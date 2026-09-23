"""Transactional executions over a persisted copy of the supplied mock data."""
from datetime import date, timedelta
import hashlib
import json
from uuid import uuid4
from app.router.validator import validate_slot_value


class BackendError(ValueError):
    def __init__(self, code, details=None):
        self.code, self.details = code, details
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class MockBackend:
    def __init__(self, dataset, repository, kb):
        self.dataset, self.repository, self.kb = dataset, repository, kb
        self.today = date.fromisoformat(dataset.as_of_date)

    def execute(self, action, parameters, operation_id, owner):
        if action not in self.dataset.actions:
            raise BackendError('invalid_input')
        definition = self.dataset.actions[action]
        for group in definition['inputs']:
            if not any(parameters.get(k) is not None for k in group.split('|')):
                raise BackendError('invalid_input', {'missing': group})
        for name, value in parameters.items():
            if name in self.dataset.slots:
                try:
                    validate_slot_value(self.dataset.slots[name], value)
                except ValueError as exc:
                    raise BackendError('invalid_input', {'slot': name}) from exc
        fingerprint = digest([owner, action, parameters])
        with self.repository.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT fingerprint,result FROM operations WHERE id=?', (operation_id,)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise BackendError('invalid_input', 'operation_id reused with different parameters or owner')
                return {**json.loads(previous['result']), 'replayed': True}
            data = json.loads(db.execute('SELECT body FROM backend WHERE id=1').fetchone()['body'])
            try:
                result = self.dispatch(data, action, parameters)
            except BackendError:
                raise
            except (KeyError,ValueError,TypeError,IndexError) as exc:
                raise BackendError('invalid_input', 'Unsupported parameters for canonical mock data') from exc
            missing = set(definition['outputs']) - result.keys()
            if missing:
                raise BackendError('service_unavailable', {'invalid_result_fields': sorted(missing)})
            envelope = {'action': action, 'operation_id': operation_id, 'result': result,
                        'mock': True, 'source_id': 'mock:' + operation_id, 'replayed': False}
            db.execute('UPDATE backend SET body=? WHERE id=1', (json.dumps(data),))
            db.execute('INSERT INTO operations VALUES(?,?,?)', (operation_id, fingerprint, json.dumps(envelope)))
            return envelope

    def dispatch(self, data, action, p):
        kb = self.kb.data
        def find(collection, predicate):
            matches = [x for x in data[collection] if predicate(x)]
            if not matches: raise BackendError('not_found')
            return matches[0]
        def policy(active=False):
            result = find('policies', lambda x: x['policy_number'] == p.get('policy_number') or
                          (p.get('vehicle_plate') is not None and x['details'].get('vehicle_plate') == p['vehicle_plate']))
            status = result.get('status') or ('active' if result['start_date'] <= str(self.today) <= result['end_date'] else 'expired' if result['end_date'] < str(self.today) else 'not_yet_active')
            if active and status != 'active': raise BackendError('policy_inactive')
            return {**result, 'status': status}
        def bm(iin):
            return next((c['bm_class'] for c in data['clients'] if c['iin'] == iin), data['defaults']['unknown_iin_bm_class'])
        def ticket(kind):
            ident = 'T-' + uuid4().hex[:10].upper()
            data.setdefault('tickets', []).append({'ticket_id': ident, 'type': kind, 'parameters': p})
            return {'ticket_id': ident}
        if action == 'find_client':
            return find('clients', lambda x: x['phone'] == p.get('phone') or x['iin'] == p.get('iin'))
        if action == 'get_policies':
            find('clients', lambda x:x['client_id'] == p['client_id'])
            return {'policies':[x for x in data['policies'] if x['client_id'] == p['client_id']]}
        if action == 'get_policy': return policy()
        if action == 'get_bm_class': return {'bm_class': bm(p['iin'])}
        if action == 'calc_ogpo_price':
            cfg = kb['products']['ogpo']['pricing']
            if not p['drivers_iin']: raise BackendError('invalid_input')
            price = cfg['base_by_region_kzt'][p['region']] * cfg['vehicle_type_coef'][p['vehicle_type']] * max(cfg['bm_coef'][bm(i)] for i in p['drivers_iin'])
            return {'price': round(price), 'term_months':12, 'source_id':'knowledge_base.json#/products/ogpo/pricing'}
        if action == 'calc_casco_price':
            cfg = kb['products']['casco']['pricing']; age = self.today.year - p['car_year']
            if age < 0 or age > cfg['max_car_age']['Standard']: raise BackendError('not_eligible')
            if p['car_value'] <= 0: raise BackendError('invalid_input')
            band = '0-3' if age <= 3 else '4-7' if age <= 7 else '8-10'
            return {'price': round(p['car_value'] * cfg['rate_by_car_age'][band] * cfg['franchise_coef'][str(p['franchise'])]), 'package':'Standard', 'source_id':'knowledge_base.json#/products/casco/pricing'}
        if action == 'calc_travel_price':
            country = p['trip_country'].casefold().strip()
            countries = {'A': ['russia','россия','ресей','georgia','грузия','uzbekistan','узбекистан','өзбекстан'],
                         'B':['france','франция','germany','германия','italy','италия','spain','испания','uk','великобритания','ұлыбритания'],
                         'C':['turkey','турция','түркия','uae','оаэ','баә','thailand','таиланд','egypt','египет','мысыр'],
                         'D':['usa','сша','ақш','canada','канада']}
            zone = next((z for z, names in countries.items() if country in names), None)
            if zone is None: raise BackendError('invalid_input', 'country zone needs operator verification')
            days = (date.fromisoformat(p['trip_end']) - date.fromisoformat(p['trip_start'])).days + 1
            if days <= 0 or p['travelers_count'] <= 0 or p['traveler_max_age'] < 0: raise BackendError('invalid_input')
            if p['traveler_max_age'] > 75: raise BackendError('not_eligible')
            z = kb['products']['travel']['zones'][zone]
            return {'price': round(z['rate_per_day_kzt'] * days * p['travelers_count'] * (2 if p['traveler_max_age'] >= 65 else 1)), 'zone':zone, 'coverage':z['coverage']}
        if action in {'calc_property_price','calc_accident_price'}:
            product = 'property' if action == 'calc_property_price' else 'accident'
            cfg = kb['products'][product]
            price = cfg['price_per_year_kzt'].get(str(p['sum_insured']))
            if price is None: raise BackendError('invalid_input')
            if product == 'property' and p['property_type'] == 'house': price *= cfg['house_coef']
            return {'price':round(price)}
        if action == 'create_policy':
            client = next((x for x in data['clients'] if x['phone'] == p['phone']), None)
            if client is None: raise BackendError('not_found', 'identify an existing demo client first')
            prefix = {'ogpo':'OGPO','casco':'CASCO','travel':'TRVL','property':'PROP','accident':'NS','dms':'DMS'}[p['product_type']]
            number = f'SQ-{prefix}-{900000 + len(data["policies"]):06}'
            data['policies'].append({'policy_number':number,'client_id':client['client_id'],'product':p['product_type'],
                'start_date':str(self.today),'end_date':str(self.today + timedelta(days=364)), 'premium':p.get('price'),
                'status':'pending_payment','details':p.copy()})
            data.setdefault('outbox', []).append({'channel':'sms','to':p['phone'],'kind':'mock_payment_link','policy_number':number})
            return {'policy_number':number,'status':'pending_payment'}
        if action == 'renew_policy':
            old = policy()
            if (date.fromisoformat(old['end_date']) - self.today).days > 30: raise BackendError('not_eligible')
            number = old['policy_number'].rsplit('-',1)[0] + f'-{900000+len(data["policies"]):06}'
            start = max(self.today, date.fromisoformat(old['end_date']) + timedelta(days=1))
            data['policies'].append({**old,'policy_number':number,'start_date':str(start),'end_date':str(start+timedelta(days=364)), 'status':'pending_payment'})
            return {'policy_number':number,'price':old['premium'],'status':'pending_payment'}
        if action == 'update_policy':
            old = policy(True); target = find('policies', lambda x:x['policy_number'] == old['policy_number'])
            if p.get('new_driver_iin'):
                drivers = target['details'].setdefault('drivers_iin', [])
                if p['new_driver_iin'] not in drivers: drivers.append(p['new_driver_iin'])
            elif p.get('vehicle_plate'): target['details']['vehicle_plate'] = p['vehicle_plate']
            else: raise BackendError('invalid_input')
            # No tariff for amendments is supplied; never invent a premium.
            return {'extra_premium':None,'note':'Premium adjustment requires operator calculation.'}
        if action == 'cancel_policy':
            old = policy()
            if old['status'] == 'cancelled': raise BackendError('already_done')
            if old['status'] != 'active': raise BackendError('policy_inactive')
            if any(c['policy_number'] == old['policy_number'] and c['status'] == 'paid' for c in data['claims']): raise BackendError('not_eligible')
            end = date.fromisoformat(old['end_date']); months = max(0,(end.year-self.today.year)*12 + end.month-self.today.month - (end.day < self.today.day))
            if old['premium'] is None: raise BackendError('not_eligible')
            refund = round(old['premium'] * months / 12 * .9)
            find('policies', lambda x:x['policy_number']==old['policy_number'])['status'] = 'cancelled'
            return {'refund_amount':refund}
        if action == 'get_claim':
            return find('claims', lambda x:x['claim_number'] == p.get('claim_number') or x['client_id'] == p.get('client_id'))
        if action == 'create_claim':
            old = policy(True)
            number = f'CL-{900000+len(data["claims"]):06}'
            data['claims'].append({'claim_number':number,'policy_number':old['policy_number'],'client_id':p.get('client_id',old['client_id']),
                'claim_type':p['product_type'],'incident_date':p['incident_date'],'description':p['incident_description'],
                'status':'registered','next_step':'Collect required documents.'})
            return {'claim_number':number}
        if action == 'create_dispute':
            find('claims', lambda x:x['claim_number']==p['claim_number'])
            return ticket(action)
        if action in {'create_complaint','report_fraud'}: return ticket(action)
        if action == 'check_payment':
            row = find('payments', lambda x:x['client_id']==p['client_id'] and x['date']==p['payment_date'])
            return {**row,'payment_status':row['status']}
        if action == 'update_contact':
            row = find('clients', lambda x:x['client_id']==p['client_id'])
            field = p['contact_field']
            if field in {'phone','email'}:
                try: validate_slot_value(self.dataset.slots[field],p['new_value'])
                except ValueError as exc: raise BackendError('invalid_input') from exc
            row[field] = p['new_value']
            return {'updated_field':field,'new_value':row[field]}
        if action in {'get_offices','list_clinics'}:
            collection = 'offices' if action=='get_offices' else 'clinics'
            matches = [x for x in kb[collection] if x['city']==p['city']]
            if not matches: raise BackendError('not_found')
            return ({**matches[0],'source_id':f'knowledge_base.json#/offices/{kb[collection].index(matches[0])}'} if action=='get_offices'
                    else {'clinics':matches,'source_id':'knowledge_base.json#/clinics'})
        if action == 'kb_lookup': return {'answer':self.kb.lookup(p['topic'])}
        if action == 'check_coverage':
            old = policy(True)
            if old['product'] != 'dms': raise BackendError('not_covered')
            package = kb['products']['dms']['packages'][old['details']['package']]
            query = p['service_name'].casefold()
            aliases = {'мрт':'MRI','кт':'CT','тіс':'Dental','стомат':'Dental','узи':'Ultrasound','узд':'Ultrasound','терапевт':'Therapist','имплант':'implants'}
            query = next((v.casefold() for k,v in aliases.items() if k in query),query)
            denied = [v for v in package['not_covered'] if query in v.casefold()]
            covered = [v for v in package['covered'] if query in v.casefold()]
            return {'covered':False if denied else True if covered else None,'note':'; '.join(denied or covered) or 'Coverage needs operator verification.', 'source_id':f'knowledge_base.json#/products/dms/packages/{old["details"]["package"]}'}
        if action in {'book_inspection','book_appointment'}:
            if action == 'book_inspection':
                find('claims', lambda x:x['claim_number']==p['claim_number'])
                candidates = [x for x in kb['inspection_points'] if x['city']==p['city']] or [x for x in kb['inspection_points'] if x['city']=='other']
                place = candidates[0]; name = place['address']
            else:
                old=policy(True)
                if old['product']!='dms': raise BackendError('not_covered')
                aliases={'терапевт':'therapist','кардиолог':'cardiologist','стоматолог':'dentist','лор':'ENT','гинеколог':'gynecologist','педиатр':'pediatrician'}
                specialty=aliases.get(p['doctor_specialty'].casefold(),p['doctor_specialty'])
                candidates=[x for x in kb['clinics'] if x['city']==p['city'] and specialty in x['specialties']]
                if not candidates: raise BackendError('not_covered')
                place=candidates[0]; name=place['name']
            day=date.fromisoformat(p['preferred_date'])
            if day < self.today or day.weekday() >= 5: raise BackendError('no_availability', {'nearest_weekday':str(self.today+timedelta(days=(7-self.today.weekday())%7 or 1))})
            bookings=data.setdefault('bookings',[])
            available=[f'{day}T{h:02}:00:00+05:00' for h in range(9,17) if not any(b['place']==name and b['time']==f'{day}T{h:02}:00:00+05:00' for b in bookings)]
            if not available: raise BackendError('no_availability')
            bookings.append({'place':name,'time':available[0],'parameters':p})
            return {'slot_datetime':available[0], **({'address':place['address']} if action=='book_inspection' else {'clinic_name':place['name']})}
        if action in {'resend_documents','request_document'}:
            old=policy(action=='resend_documents')
            client=find('clients', lambda x:x['client_id']==old['client_id'])
            email=p.get('email') or client['email']
            data.setdefault('outbox',[]).append({'channel':'email','to':email,'kind':action,'parameters':p})
            return {'sent_to':email}
        if action in {'send_sms','create_callback','transfer_to_operator'}:
            if action=='transfer_to_operator' and p['queue'] not in self.dataset.documents['actions.json']['queues']: raise BackendError('invalid_input')
            data.setdefault('outbox',[]).append({'kind':action,'parameters':p})
            return {'recorded':True,'channel':'mock'}
        raise BackendError('invalid_input')
