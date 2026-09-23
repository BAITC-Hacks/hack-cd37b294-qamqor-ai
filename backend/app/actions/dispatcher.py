from uuid import uuid4
from app.actions.mock_backend import BackendError, digest
from app.kb.service import SECTIONS


PRODUCTS = {'SC01':'ogpo','SC02':'ogpo','SC03':'casco','SC06':'travel','SC07':'property','SC08':'accident',
            'SC12':'ogpo','SC13':'casco','SC14':'property','SC16':'accident'}


class Dispatcher:
    def __init__(self, dataset, backend, slots, kb):
        self.dataset, self.backend, self.slots, self.kb = dataset, backend, slots, kb

    def run(self, state, topic, decision, confirmation=None):
        scenario = self.dataset.scenarios[topic]
        values = self.slots.values(state, topic)
        context = dict(values)
        if topic in PRODUCTS: context.setdefault('product_type',PRODUCTS[topic])
        context.setdefault('topic', SECTIONS.get(topic, 'products.' + context['product_type'] if context.get('product_type') else 'company'))
        calls, sources = [], []
        completed = state['completed_actions'].setdefault(topic,{})

        def call(action, params, operation=None):
            key = digest([action,params])
            if key in completed:
                return completed[key]
            attempts = 0
            while True:
                try:
                    result = self.backend.execute(action,params,operation or str(uuid4()),state['conversation_id'])
                    calls.append(result)
                    completed[key] = result
                    return result
                except BackendError as exc:
                    calls.append({'action':action,'error':{'code':exc.code,'details':exc.details},'mock':True})
                    if exc.code == 'service_unavailable' and attempts == 0:
                        attempts += 1
                        continue
                    raise

        def result(phase, **extra):
            return {'phase':phase,'backend_actions':calls,'kb_lookups':sources, **extra}

        try:
            if 'kb_lookup' in scenario['actions']:
                source = self.kb.for_scenario(topic,values)
                sources.append(source)
                context['topic'] = source['source_id'].split('#/')[1].replace('/','.')
            missing = self.slots.missing(state,topic)
            if missing:
                return result('collect',missing=missing,question=self.slots.question(missing[0],state['response_language']))
            if context.get('policy_number') and any(a in scenario['actions'] for a in ['find_client','get_policy','create_claim']):
                item = call('get_policy',{'policy_number':context['policy_number']})
                context.update({k:v for k,v in item['result'].items() if k in {'client_id','product','policy_number'}})
                context.setdefault('product_type',context.get('product'))
            if topic == 'SC12':
                item = call('get_policy',{'vehicle_plate':context['culprit_vehicle_plate']})
                context['policy_number'] = item['result']['policy_number']
            for action in scenario['actions']:
                if action == 'find_client' and context.get('client_id'): continue
                if action == 'get_bm_class' and not context.get('iin'):
                    if context.get('new_driver_iin'): context['iin'] = context['new_driver_iin']
                    else: continue  # calc_ogpo_price checks all drivers independently
                if action == 'send_sms' and not context.get('phone'): continue
                if action == 'transfer_to_operator':
                    handoff = scenario.get('handoff')
                    allowed = decision.action == 'HANDOFF' or bool(handoff and handoff['when'].startswith('always'))
                    allowed |= topic == 'SC30' and context.get('payment_status') == 'charged_policy_not_issued'
                    allowed |= topic == 'SC11' and context.get('injured') is True
                    if not allowed: continue
                    context['queue'] = handoff['queue'] if handoff else 'operator_general'
                if action == 'get_policies' and context.get('policy_number'): continue
                if action == 'resend_documents' and not context.get('policy_number'):
                    policies = context.get('policies',[])
                    if len(policies) == 1: context['policy_number'] = policies[0]['policy_number']
                definition = self.dataset.actions[action]
                missing = [group.split('|')[0] for group in definition['inputs'] if not any(context.get(k) is not None for k in group.split('|'))]
                if missing:
                    return result('collect',missing=missing,question=self.slots.question(missing[0],state['response_language']))
                names = {k for group in definition['inputs'] for k in group.split('|')}
                if action in {'update_policy','create_policy','create_claim'}:
                    names |= set(values) | {'product_type','price','policy_number','client_id'}
                params = {k:v for k,v in context.items() if k in names and v is not None}
                key = digest([action,params])
                if key in completed:
                    context.update(completed[key]['result'])
                    continue
                operation = None
                if definition['irreversible']:
                    pending = state.get('pending_action')
                    matches = pending and pending['action'] == action and pending['parameters'] == params and pending['topic_id'] == topic
                    if confirmation and matches and confirmation == pending['operation_id']:
                        operation = pending['operation_id']
                    else:
                        if not matches:
                            pending = {'operation_id':str(uuid4()),'action':action,'parameters':params,'topic_id':topic,
                                       'state_version':state['state_version'],'status':'awaiting_confirmation'}
                        state['pending_action'] = pending
                        return result('confirm',pending_action=pending)
                item = call(action,params,operation)
                context.update(item['result'])
                if operation: state['pending_action'] = None
            return result('completed',results=[v for v in completed.values()])
        except BackendError as exc:
            return result('error',error={'code':exc.code,'details':exc.details})
