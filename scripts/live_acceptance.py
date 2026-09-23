"""Real HTTP + real L2 acceptance. No official evaluation predictions are substituted."""
import asyncio
import json
from pathlib import Path
from statistics import mean
from uuid import uuid4
import httpx

OUT=Path('evaluation/product-acceptance')


async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records=[]; results={}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=240) as client:
        async def session(language='ru'):
            r=await client.post('/api/session',json={'language':language});r.raise_for_status();return r.json()
        async def send(s,text,**kwargs):
            body={'conversation_id':s['conversation_id'],'turn_id':str(uuid4()),'text':text,'expected_state_version':s['state_version'],**kwargs}
            r=await client.post('/api/chat',json=body)
            records.append({'request':body,'status':r.status_code,'response':r.json()})
            (OUT/'turns.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            r.raise_for_status();value=r.json()
            state=(await client.get('/api/session/'+s['conversation_id'])).json();s.clear();s.update(state)
            trace=(await client.get('/api/supervisor/session/'+s['conversation_id'])).json()
            event=next(x for x in trace['events'] if x.get('turn_id')==body['turn_id'] and x.get('proposal'))
            print(json.dumps({'text':text,'answer':value['text'],'route':event['decision']['action'],'scenarios':event['decision']['scenarios'],'total_ms':value['latency']['total_text_ms']},ensure_ascii=False),flush=True)
            return value,event,body
        async def check(name,fn):
            try: await fn();results[name]='PASS'
            except Exception as exc: results[name]=f'FAIL: {type(exc).__name__}: {exc}'
            (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        async def office():
            s=await session();r,e,_=await send(s,'Где находится ваш офис в Алматы?')
            assert e['decision']['scenarios']==['SC33'] and 'Abai Ave 150' in r['text'] and r['citations']
        async def boundary():
            s=await session();r,e,_=await send(s,'Ақша списали, бірақ полис келмеді')
            assert e['decision']['action']=='CLARIFY' and not e['backend_actions']
            r,e,_=await send(s,'Полис вообще не выпустился после оплаты. Мой телефон +77010000003, оплата была 30 сентября 2026 года.')
            assert e['decision']['scenarios']==['SC30']
            assert any(x.get('action')=='check_payment' and x.get('result',{}).get('payment_status')=='charged_policy_not_issued' for x in e['backend_actions'])
        async def correction_action():
            s=await session();r,e,_=await send(s,'Хочу изменить email. Мой ИИН 850314300121, новый адрес first@example.com.')
            assert r['pending_action'];old=r['pending_action']['operation_id']
            r,e,_=await send(s,'Нет, ошибся: новый email second@example.com.')
            assert r['pending_action'] and r['pending_action']['operation_id']!=old
            assert any(x.get('supersedes') for x in s['evidence'])
            token=r['pending_action']['operation_id']
            r,e,_=await send(s,'Подтверждаю',confirm_operation_id=old)
            assert any(x.get('code')=='stale_confirmation' for x in e['errors'])
            r,e,body=await send(s,'Подтверждаю',confirm_operation_id=token)
            assert r['pending_action'] is None
            assert any(x.get('action')=='update_contact' and x.get('result',{}).get('new_value')=='second@example.com' for x in e['backend_actions'])
            repeat=await client.post('/api/chat',json=body);assert repeat.json()==r
        async def switch_restore():
            s=await session();await send(s,'Хочу расторгнуть полис SQ-OGPO-105120: продал машину.')
            r,e,_=await send(s,'Кстати, где ваш офис в Алматы?')
            assert e['decision']['action']=='SWITCH' and 'SC28' in s['topic_stack']
            r,e,_=await send(s,'Вернёмся к расторжению моего полиса.')
            assert e['decision']['action']=='RESTORE' and s['active_scenario']=='SC28'
        async def kazakh():
            s=await session('kk');r,e,_=await send(s,'Алматыдағы кеңсеңіз қайда орналасқан? Қазақша жауап беріңізші.')
            assert r['language']=='kk' and 'Жұмыс уақыты' in r['text']
        async def missing():
            s=await session();r,e,_=await send(s,'Хочу поменять email.')
            assert e['decision']['scenarios']==['SC29'] and not r['pending_action'] and s['pending_questions']
        for name,fn in [('obvious_office',office),('ambiguous_boundary_backend',boundary),('correction_confirmation_idempotency',correction_action),('switch_restore',switch_restore),('kazakh',kazakh),('missing_slots',missing)]: await check(name,fn)
    latencies=[x['response']['latency']['total_text_ms'] for x in records if x['status']==200]
    results['measured_turns']=len(latencies);results['average_total_text_ms']=mean(latencies) if latencies else None
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
    return 1 if any(str(v).startswith('FAIL') for v in results.values()) else 0

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
