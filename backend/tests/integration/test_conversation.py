import asyncio
import json
from types import SimpleNamespace
import httpx
import pytest
from app.main import create_app
from app.config.settings import Settings
from app.router.schemas import RouterProposal, SlotUpdate
from app.state.models import new_state
from app.state.repository import Repository
from app.slots.manager import SlotManager
from app.actions.mock_backend import MockBackend, BackendError
from app.kb.service import KnowledgeBase


def proposal(topic, turn, slots=None, relation='new', supersedes=None, language='ru'):
    return RouterProposal.model_validate(dict(scenarios=[topic], alternatives=[], system_intent=None,
        evidence=[dict(evidence_id=turn+'e',fact='test fixture',source_type='user_turn',source_id=turn,
                       quote='test',polarity='positive',supersedes=supersedes)],boundary_checks=[],
        slot_updates=[dict(slot_id=k,raw_value=v,normalized_value=v,source_turn_id=turn,topic_id=topic) for k,v in (slots or {}).items()],
        input_language=language,response_language=language,confidence=.9,topic_relation=relation,clarification_question=None,reason='test fixture'))


class FixtureRouter:
    def __init__(self, outputs): self.outputs=iter(outputs); self.requests=[]
    async def route(self, request, *args):
        self.requests.append(request)
        return SimpleNamespace(proposal=next(self.outputs),latency_ms=1,retry_count=0,attempts=[{}])


def test_session_state_corrections_confirmation_and_replay(tmp_path):
    async def run():
        app=create_app(Settings(api_key='fixture'),database_path=tmp_path/'db.sqlite')
        async with app.router.lifespan_context(app):
            router=FixtureRouter([
                proposal('SC29','t1',{'iin':'850314300121','contact_field':'email','new_value':'first@example.com'}),
                proposal('SC29','t2',{'new_value':'second@example.com'},'continue','t1e'),
                proposal('SC29','t3',relation='continue'),
                proposal('SC29','t4',relation='continue'),
                proposal('SC33','t5',{'city':'Almaty'}),
                proposal('SC29','t6',relation='restore'),
            ])
            app.state.conversations.router=router
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
                created=await client.post('/api/session',json={'language':'ru'})
                assert created.status_code==200,created.text
                cid=created.json()['conversation_id']
                async def send(turn, **kw):
                    r=await client.post('/api/chat',json={'conversation_id':cid,'turn_id':turn,'text':'test',**kw})
                    assert r.status_code==200,r.text
                    return r.json()
                first=await send('t1'); old=first['pending_action']['operation_id']
                second=await send('t2'); new=second['pending_action']['operation_id']
                assert old!=new
                stale=await send('t3',confirm_operation_id=old,expected_state_version=2)
                assert 'устарело' in stale['text']
                confirmed=await send('t4',confirm_operation_id=new,expected_state_version=3)
                assert confirmed['pending_action'] is None and 'second@example.com' in confirmed['text']
                assert await send('t4',confirm_operation_id=new,expected_state_version=3)==confirmed
                with app.state.repository.connect() as db:
                    data=json.loads(db.execute('SELECT body FROM backend').fetchone()['body'])
                    operations=[json.loads(r['result']) for r in db.execute('SELECT result FROM operations')]
                assert next(x for x in data['clients'] if x['client_id']=='C001')['email']=='second@example.com'
                assert len([x for x in operations if x['action']=='update_contact'])==1
                await send('t5')
                state=(await client.get('/api/session/'+cid)).json()
                assert state['active_scenario']=='SC33' and state['topic_stack']==['SC29']
                await send('t6')
                state=(await client.get('/api/session/'+cid)).json()
                assert state['active_scenario']=='SC29'
                assert state['slots_by_topic']['SC29']['new_value']['superseded_values'][0]['normalized_value']=='first@example.com'
                assert all(e.evidence_id!='t1e' for e in router.requests[-1].known_evidence)
                events=(await client.get('/api/supervisor/session/'+cid)).json()['events']
                assert len(events)==6 and any(e['decision']['action']=='RESTORE' for e in events)
                bad=await client.post('/api/chat',json={'conversation_id':cid,'turn_id':'t7','text':'test','expected_state_version':0})
                assert bad.status_code==409
    asyncio.run(run())


def test_backend_idempotency_and_errors(dataset,tmp_path):
    repository=Repository(tmp_path/'db.sqlite',dataset.documents['mock_backend.json'])
    backend=MockBackend(dataset,repository,KnowledgeBase(dataset))
    params={'client_id':'C001','contact_field':'email','new_value':'new@example.com'}
    first=backend.execute('update_contact',params,'op1','owner')
    second=backend.execute('update_contact',params,'op1','owner')
    assert first['result']==second['result'] and second['replayed']
    for changed in [{**params,'new_value':'other@example.com'},params]:
        with pytest.raises(BackendError): backend.execute('update_contact',changed,'op1','other-owner')
    with pytest.raises(BackendError,match='not_found'): backend.execute('get_policy',{'policy_number':'SQ-OGPO-000000'},'op2','owner')
    with pytest.raises(BackendError,match='not_eligible'): backend.execute('cancel_policy',{'policy_number':'SQ-CASCO-204118','cancel_reason':'sold'},'op3','owner')


def test_slots_scoped_and_missing(dataset):
    slots=SlotManager(dataset); state=new_state()
    slots.apply(state,[SlotUpdate(slot_id='city',raw_value='Almaty',normalized_value='Almaty',source_turn_id='t1',topic_id='SC33')],'SC33',1)
    assert slots.values(state,'SC33')['city']=='Almaty'
    assert 'city' not in slots.values(state,'SC22')
    assert slots.missing(state,'SC33')==[]
    assert slots.missing(state,'SC22')


def test_kb_provenance_and_unknown(dataset):
    kb=KnowledgeBase(dataset)
    assert kb.lookup('offices.0')['value']==dataset.documents['knowledge_base.json']['offices'][0]
    assert kb.lookup('offices.0')['source_id']=='knowledge_base.json#/offices/0'
    with pytest.raises(ValueError): kb.lookup('invented.product')


def test_secondary_intent_survives_followup_and_can_be_restored(tmp_path):
    async def run():
        app=create_app(Settings(api_key='fixture'),database_path=tmp_path/'db.sqlite')
        async with app.router.lifespan_context(app):
            first=proposal('SC33','t1',{'city':'Almaty'});first.scenarios.append('SC29')
            router=FixtureRouter([first,proposal('SC33','t2',relation='continue'),proposal('SC29','t3',relation='restore')])
            service=app.state.conversations;service.router=router;s=service.create()
            from app.state.models import ChatRequest
            for turn in ['t1','t2','t3']:
                await service.chat(ChatRequest(conversation_id=s['conversation_id'],turn_id=turn,text='test'))
                if turn!='t3':assert 'SC29' in service.get(s['conversation_id'])['unresolved_topics']
            assert 'SC29' in router.requests[-1].topic_stack
            assert service.get(s['conversation_id'])['active_scenario']=='SC29'
    asyncio.run(run())


def test_failed_backend_is_traced_and_never_reports_success(tmp_path):
    async def run():
        app=create_app(Settings(api_key='fixture'),database_path=tmp_path/'db.sqlite')
        async with app.router.lifespan_context(app):
            service=app.state.conversations;service.router=FixtureRouter([proposal('SC33','t1',{'city':'Almaty'})])
            count=0
            def unavailable(*args):
                nonlocal count
                count+=1
                raise BackendError('service_unavailable')
            service.dispatcher.backend.execute=unavailable
            s=service.create()
            from app.state.models import ChatRequest
            result=await service.chat(ChatRequest(conversation_id=s['conversation_id'],turn_id='t1',text='test'))
            assert count==2 and 'недоступен' in result['text']
            event=service.tracer.events(s['conversation_id'])[0]
            assert event['errors'][0]['code']=='service_unavailable'
            assert not service.get(s['conversation_id'])['latest_backend_results']
    asyncio.run(run())
