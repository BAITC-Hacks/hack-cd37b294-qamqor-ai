import asyncio
from copy import deepcopy
import json
import time
from uuid import uuid4
from fastapi import HTTPException
from app.router.schemas import RouterInput, Turn, EvidenceItem, SourceRecord
from app.policy.rules import reanalysis_reason
from app.state.models import now, new_state


class ConversationService:
    def __init__(self, repository, router, policy, slots, dispatcher, composer, tracer):
        self.repository,self.router,self.policy,self.slots,self.dispatcher,self.composer,self.tracer = repository,router,policy,slots,dispatcher,composer,tracer
        self.locks={}

    def create(self, language='ru'):
        state=new_state(language)
        self.repository.save(state)
        return state

    def get(self, conversation_id):
        state=self.repository.get(conversation_id)
        if state is None: raise HTTPException(404,'Session not found')
        return state

    async def chat(self, body):
        async with self.locks.setdefault(body.conversation_id,asyncio.Lock()):
            return await self._turn(body)

    async def _turn(self, body):
        started=time.perf_counter()
        before=self.get(body.conversation_id)
        signature=json.dumps({'text':body.text,'confirm':body.confirm_operation_id,'language':body.language,'mode':body.input_mode},sort_keys=True)
        previous=self.repository.previous_turn(body.conversation_id,body.turn_id)
        if previous:
            if previous['request'] != signature: raise HTTPException(409,'turn_id already used for another request')
            return json.loads(previous['response'])
        if body.expected_state_version is not None and body.expected_state_version != before['state_version']:
            raise HTTPException(409,'State changed; refresh before confirming')
        if body.confirm_operation_id and body.expected_state_version is None:
            raise HTTPException(409,'Confirmation requires the preview state version')
        state=deepcopy(before)
        if body.language in {'ru','kk'}: state['response_language']=body.language
        retired={e['supersedes'] for e in state['evidence'] if e.get('supersedes')}
        request=RouterInput(current_user_turn=Turn(turn_id=body.turn_id,role='user',text=body.text),
            history=[Turn(**t) for t in state['history']],active_scenario=state['active_scenario'],topic_stack=list(dict.fromkeys([*state['topic_stack'],*state['unresolved_topics']])),
            current_slots=self.slots.router_slots(state),known_evidence=[EvidenceItem(**e) for e in state['evidence'] if e['evidence_id'] not in retired],
            pending_action=state['pending_action']['action'] if state['pending_action'] else None,
            latest_backend_results=[SourceRecord(**r) for r in state['latest_backend_results']],response_language=state['response_language'])
        result=await self.router.route(request,reanalysis_reason)
        if not result.proposal:
            self.tracer.emit({'event_id':str(uuid4()),'conversation_id':body.conversation_id,'turn_id':body.turn_id,
                'timestamp':now(),'type':'router_error','user_text':body.text,'response':None,'state_before':before,'state_after':before,
                'errors':[{'kind':result.error_kind,'message':result.error}],'retry_count':result.retry_count,
                'latency':{'router_ms':result.latency_ms,'total_text_ms':(time.perf_counter()-started)*1000}})
            raise HTTPException(502,{'kind':result.error_kind,'message':result.error})
        tick=time.perf_counter(); decision=self.policy.decide(result.proposal,request); policy_ms=(time.perf_counter()-tick)*1000
        proposal=result.proposal
        state['turn_number']+=1; state['state_version']+=1; state['updated_at']=now()
        state['language']=proposal.input_language; state['response_language']=proposal.response_language
        state['active_scenario']=decision.next_active_scenario; state['topic_stack']=decision.next_topic_stack
        state['unresolved_topics']=[topic for topic in dict.fromkeys([*before['unresolved_topics'],*decision.next_topic_stack,*decision.deferred_scenarios,*decision.scenarios[1:]]) if topic!=state['active_scenario']]
        if decision.action=='END': state['unresolved_topics']=[]
        state['evidence'].extend(e.model_dump() for e in proposal.evidence)
        changes=self.slots.apply(state,proposal.slot_updates,decision.scenarios[0] if decision.scenarios else state['active_scenario'],state['state_version'])
        pending=before['pending_action']
        invalidated=bool(pending and (changes or state['active_scenario'] != pending['topic_id']))
        if changes:
            if any(c['scope']=='__identity__' for c in changes):
                state['completed_actions']={}; state['latest_backend_results']=[]
            else:
                for scope in {c['scope'] for c in changes}: state['completed_actions'].pop(scope,None)
        if invalidated: state['pending_action']=None
        confirmation=body.confirm_operation_id
        valid_confirmation=bool(confirmation and pending and not invalidated and pending['operation_id']==confirmation
                                and pending['state_version']==before['state_version'])
        backend_start=time.perf_counter()
        if confirmation and not valid_confirmation:
            outcome={'phase':'error','error':{'code':'stale_confirmation'}}
        elif valid_confirmation:
            outcome=self.dispatcher.run(state,pending['topic_id'],decision,confirmation)
        elif decision.action=='CLARIFY': outcome={'phase':'clarify'}
        elif decision.scenarios:
            topic=decision.next_active_scenario or decision.scenarios[0]
            outcome=self.dispatcher.run(state,topic,decision)
        else: outcome={'phase':'system'}
        backend_ms=(time.perf_counter()-backend_start)*1000
        if state['pending_action']:
            state['pending_action']['state_version']=state['state_version']
        state['pending_questions']=[outcome['question']] if outcome.get('question') else ([decision.clarification_question] if decision.action=='CLARIFY' and not valid_confirmation else [])
        for call in outcome.get('backend_actions',[]):
            if call.get('source_id'):
                state['latest_backend_results'].append({'source_id':call['source_id'],'content':json.dumps(call['result'],ensure_ascii=False)})
        state['latest_backend_results']=state['latest_backend_results'][-20:]
        tick=time.perf_counter(); answer,citations=await self.composer.compose(state,decision,outcome); compose_ms=(time.perf_counter()-tick)*1000
        state['history'].extend([{'turn_id':body.turn_id,'role':'user','text':body.text},{'turn_id':body.turn_id+':assistant','role':'assistant','text':answer}])
        latency={'stt_ms':body.stt_latency_ms,'router_ms':result.latency_ms,'policy_ms':policy_ms,'backend_ms':backend_ms,
                 'response_composition_ms':compose_ms,'tts_ms':None,'total_text_ms':(time.perf_counter()-started)*1000}
        event={'event_id':str(uuid4()),'conversation_id':body.conversation_id,'turn_id':body.turn_id,'timestamp':now(),
               'user_text':body.text,'response':answer,'proposal':proposal.model_dump(),'decision':decision.model_dump(),
               'slots_changed':changes,'backend_actions':outcome.get('backend_actions',[]),'kb_lookups':outcome.get('kb_lookups',[]),
               'citations':citations,'state_before':before,'state_after':deepcopy(state),'pending_invalidated':invalidated,
               'llm_calls':len(result.attempts),'composition_llm_calls':outcome.get('composition_llm_calls',0),
               'retry_count':result.retry_count,'errors':[outcome[k] for k in ('error','composition_error') if outcome.get(k)],
               'latency':latency,'input_mode':body.input_mode,
               'request_metrics':[{k:v for k,v in a.items() if k not in {'request_payload','raw_response'}} for a in result.attempts]}
        response={'conversation_id':body.conversation_id,'turn_id':body.turn_id,'text':answer,'language':state['response_language'],
                  'state_version':state['state_version'],'pending_action':state['pending_action'],'latency':latency,
                  'citations':citations,'event_id':event['event_id'],'mock_backend':True}
        self.repository.save(state,(body.turn_id,signature,json.dumps(response)))
        self.tracer.emit(event)
        return response
