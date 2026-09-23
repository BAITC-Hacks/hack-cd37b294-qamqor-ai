import json
import re
import httpx


ACTION_NAMES = {
 'update_contact':('изменить контактные данные','байланыс деректерін өзгерту'),
 'update_policy':('изменить полис','полисті өзгерту'), 'cancel_policy':('расторгнуть полис','полисті тоқтату'),
 'renew_policy':('продлить полис','полисті ұзарту'), 'create_policy':('создать полис и запрос оплаты','полис пен төлем сұрауын жасау'),
 'create_claim':('зарегистрировать страховое событие','сақтандыру оқиғасын тіркеу'),
 'create_dispute':('зарегистрировать несогласие','келіспеушілікті тіркеу'),
 'book_inspection':('записать на осмотр','көлікті тексеруге жазу'),
 'book_appointment':('записать к врачу','дәрігерге жазу')}


class Composer:
    def __init__(self, settings, client):
        self.settings, self.client = settings, client

    async def compose(self, state, decision, outcome):
        kk = state['response_language'] == 'kk'
        phase = outcome['phase']
        if phase == 'confirm':
            p = outcome['pending_action']
            label = ACTION_NAMES.get(p['action'],('выполнить операцию','операцияны орындау'))[int(kk)]
            labels={'policy_number':('полис','полис'),'phone':('телефон','телефон'),'new_value':('новое значение','жаңа мән'),
                'contact_field':('поле','өріс'),'new_driver_iin':('ИИН водителя','жүргізуші ЖСН'), 'vehicle_plate':('госномер','мемлекеттік нөмір'),
                'cancel_reason':('причина','себеп'),'preferred_date':('дата','күн'),'city':('город','қала'),
                'doctor_specialty':('врач','дәрігер'),'claim_number':('обращение','өтініш'),'complaint_text':('текст','мәтін'),
                'incident_date':('дата события','оқиға күні'),'incident_description':('событие','оқиға'),'price':('стоимость','құны'),
                'trip_country':('страна','ел'),'trip_start':('начало поездки','сапар басы'),'trip_end':('конец поездки','сапар соңы'),
                'travelers_count':('число туристов','туристер саны'),'traveler_max_age':('старший возраст','ең үлкен жас'),
                'drivers_iin':('ИИН водителей','жүргізушілер ЖСН'),'region':('регион','өңір'),'vehicle_type':('тип транспорта','көлік түрі')}
            details = ', '.join(f'{labels[k][int(kk)]}: {v}' for k,v in p['parameters'].items() if k in labels)
            return (f'Демо-жүйеде {label} үшін растаңыз. {details}. «Растау» түймесін басыңыз.' if kk else
                    f'Подтвердите: {label} в демо-системе. {details}. Нажмите «Подтвердить».'), []
        if phase == 'collect': return outcome['question'], []
        if phase == 'clarify': return decision.clarification_question, []
        if phase == 'error':
            labels = {'not_found':('Запись не найдена. Проверьте номер или обратитесь к оператору.','Жазба табылмады. Нөмірді тексеріңіз немесе операторға жүгініңіз.'),
                      'invalid_input':('Проверьте переданные данные. Операция не выполнена.','Деректерді тексеріңіз. Операция орындалмады.'),
                      'policy_inactive':('Полис не действует; операция недоступна.','Полис қолданыста емес; операция қолжетімсіз.'),
                      'not_eligible':('Условия продукта не позволяют выполнить операцию. Можно обратиться к оператору.','Өнім шарттары бұл операцияға мүмкіндік бермейді. Операторға жүгінуге болады.'),
                      'not_covered':('Услуга недоступна по этим условиям. Уточним альтернативу у оператора.','Осы шарттар бойынша қызмет қолжетімсіз. Баламаны оператордан анықтауға болады.'),
                      'no_availability':('На эту дату нет свободного времени. Выберите другой рабочий день.','Бұл күнге бос уақыт жоқ. Басқа жұмыс күнін таңдаңыз.'),
                      'already_done':('Операция уже выполнена.','Операция бұрын орындалған.'),
                      'stale_confirmation':('Подтверждение устарело: данные или тема изменились. Проверьте новое предложение.','Растау ескірді: деректер немесе тақырып өзгерді. Жаңа ұсынысты тексеріңіз.')}
            return labels.get(outcome['error']['code'],('Сервис недоступен. Попробуйте позже или обратитесь к оператору.','Қызмет қолжетімсіз. Кейінірек қайталаңыз немесе операторға жүгініңіз.'))[int(kk)], []
        if decision.action == 'END': return ('Сау болыңыз! Қажет болса, қайта хабарласыңыз.' if kk else 'До свидания! Обращайтесь, если понадобится помощь.'), []
        if decision.action == 'RESPOND_OUT_OF_SCOPE': return ('Бұл сұрақ біздің сақтандыру қызметтерімізге кірмейді.' if kk else 'Этот вопрос не входит в наши страховые услуги.'), []
        records = outcome.get('results') or outcome.get('backend_actions',[])
        office = next((r for r in records if r.get('action')=='get_offices' and r.get('result')),None)
        if office:
            r = office['result']
            return (f"{r['city']}: {r['address']}. Жұмыс уақыты: {r['hours']}." if kk else f"Офис в {r['city']}: {r['address']}. Часы работы: {r['hours']}."), [r['source_id']]
        contacts = next((r for r in records if r.get('action')=='update_contact'),None)
        if contacts:
            value=contacts['result']['new_value']
            return (f'Демо-жүйеде байланыс деректері жаңартылды: {value}.' if kk else f'Контактные данные в демо-системе обновлены: {value}.'),[contacts['source_id']]
        facts = [{'source_id':r['source_id'],'value':r['result']} for r in records if r.get('result') is not None]
        facts += outcome.get('kb_lookups',[])
        if not facts:
            return ('Сұрағыңызды нақтылап жазыңызшы.' if kk else 'Уточните, пожалуйста, что нужно сделать.'), []
        # Separate customer composition; never changes routing or executes an action.
        instructions = ('Write a concise, natural insurance contact-center response in ' + ('Kazakh' if kk else 'Russian') +
            '. Use ONLY supplied facts. No invented numbers, terms, addresses or eligibility. This is a fictional Saqta Insurance demo. '
            'Backend actions are mock executions: distinguish a recorded demo action from real delivery/booking/payment. '
            'Never claim an active policy if status is pending_payment. Never show scenario IDs, backend action names or raw field names. '
            'Return JSON with answer and source_ids; cite only provided source_ids. Say unknown when data is absent.')
        try:
            outcome['composition_llm_calls']=1
            response = await self.client.post(self.settings.base_url+'/responses',headers={'Authorization':'Bearer '+self.settings.api_key},
                json={'model':self.settings.model,'reasoning':{'effort':'low'},'store':False,'max_output_tokens':1200,
                    'input':[{'role':'system','content':instructions},{'role':'user','content':json.dumps(facts,ensure_ascii=False)}],
                    'text':{'format':{'type':'json_schema','name':'customer_answer','strict':True,'schema':{'type':'object','additionalProperties':False,
                        'properties':{'answer':{'type':'string'},'source_ids':{'type':'array','items':{'type':'string'}}},'required':['answer','source_ids']}}}},timeout=45)
            response.raise_for_status()
            body=response.json()
            text=''.join(c.get('text','') for i in body.get('output',[]) if i.get('type')=='message' for c in i.get('content',[]) if c.get('type')=='output_text')
            value=json.loads(text)
            assert body.get('status')=='completed' and value['source_ids'] and set(value['source_ids']) <= {f['source_id'] for f in facts}
            assert not re.search(r'\bSC\d{2}\b',value['answer'])
            # New numerical claims cannot appear outside the authoritative inputs.
            normalize=lambda text: re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))','',text)
            numbers=set(re.findall(r'\d+',normalize(json.dumps(facts,ensure_ascii=False))))
            assert set(re.findall(r'\d+',normalize(value['answer']))) <= numbers
            return value['answer'],value['source_ids']
        except (httpx.HTTPError, ValueError, KeyError, AssertionError) as exc:
            outcome['composition_error']={'code':'composition_unavailable','kind':type(exc).__name__}
            return ('Деректер алынды, бірақ жауапты қалыптастыру уақытша қолжетімсіз. Операторға жүгініңіз.' if kk else
                    'Данные получены, но сформировать ответ сейчас не удалось. Обратитесь к оператору.'), [f['source_id'] for f in facts]
