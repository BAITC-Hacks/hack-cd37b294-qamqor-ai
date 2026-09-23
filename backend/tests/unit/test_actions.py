from uuid import uuid4
import pytest
from app.actions.mock_backend import MockBackend,BackendError
from app.kb.service import KnowledgeBase
from app.state.repository import Repository


PARAMETERS={
 'find_client':{'phone':'+77010000001'},'get_policies':{'client_id':'C001'},'get_policy':{'policy_number':'SQ-OGPO-104501'},
 'get_bm_class':{'iin':'850314300121'},'calc_ogpo_price':{'region':'almaty','vehicle_type':'car','drivers_iin':['850314300121']},
 'calc_casco_price':{'car_value':10000000,'car_year':2023,'franchise':50000},
 'calc_travel_price':{'trip_country':'Turkey','trip_start':'2026-10-10','trip_end':'2026-10-20','travelers_count':2,'traveler_max_age':40},
 'calc_property_price':{'property_type':'apartment','sum_insured':5000000},'calc_accident_price':{'sum_insured':1000000},
 'create_policy':{'product_type':'ogpo','phone':'+77010000001','price':30400},'renew_policy':{'policy_number':'SQ-OGPO-102850'},
 'update_policy':{'policy_number':'SQ-OGPO-104501','new_driver_iin':'920607400233'},
 'cancel_policy':{'policy_number':'SQ-OGPO-105120','cancel_reason':'sold'},
 'create_claim':{'product_type':'casco','incident_date':'2026-09-30','incident_description':'damage','policy_number':'SQ-CASCO-204118'},
 'get_claim':{'claim_number':'CL-500330'},'create_dispute':{'claim_number':'CL-500330','complaint_text':'Review decision'},
 'book_inspection':{'claim_number':'CL-500330','city':'Almaty','preferred_date':'2026-10-02'},
 'book_appointment':{'policy_number':'SQ-DMS-604220','doctor_specialty':'therapist','city':'Astana','preferred_date':'2026-10-02'},
 'check_coverage':{'policy_number':'SQ-DMS-604220','service_name':'MRI'},'list_clinics':{'city':'Almaty'},
 'resend_documents':{'policy_number':'SQ-OGPO-104501'},'check_payment':{'client_id':'C003','payment_date':'2026-09-30'},
 'update_contact':{'client_id':'C001','contact_field':'email','new_value':'test@example.com'},
 'request_document':{'policy_number':'SQ-OGPO-104501','document_type':'policy_duplicate','email':'test@example.com'},
 'get_offices':{'city':'Almaty'},'kb_lookup':{'topic':'company'},'send_sms':{'phone':'+77010000001'},
 'create_callback':{'phone':'+77010000001','callback_time':'2026-10-02T10:00:00+05:00'},
 'create_complaint':{'complaint_text':'Service complaint'},'report_fraud':{'fraud_details':'Unexpected SMS'},
 'transfer_to_operator':{'queue':'operator_general'},
}


@pytest.mark.parametrize('action',list(PARAMETERS))
def test_every_canonical_action_executes_and_replays(action,dataset,tmp_path):
    repo=Repository(tmp_path/'db.sqlite',dataset.documents['mock_backend.json']);backend=MockBackend(dataset,repo,KnowledgeBase(dataset))
    op=str(uuid4());first=backend.execute(action,PARAMETERS[action],op,'test');second=backend.execute(action,PARAMETERS[action],op,'test')
    assert set(dataset.actions[action]['outputs'])<=first['result'].keys()
    assert second['replayed'] and second['result']==first['result']


def test_complete_action_coverage(dataset):
    assert set(PARAMETERS)==set(dataset.actions)


def test_tariff_outputs_match_official_formulas(dataset,tmp_path):
    backend=MockBackend(dataset,Repository(tmp_path/'db.sqlite',dataset.documents['mock_backend.json']),KnowledgeBase(dataset))
    def run(a):return backend.execute(a,PARAMETERS[a],str(uuid4()),'test')['result']
    assert run('calc_ogpo_price')['price']==30400
    assert run('calc_casco_price')['price']==360000
    assert run('calc_travel_price')['price']==24200
    assert run('calc_property_price')['price']==15000
    assert run('calc_accident_price')['price']==6000


def test_bad_parameters_are_safe_and_do_not_commit(dataset,tmp_path):
    repo=Repository(tmp_path/'db.sqlite',dataset.documents['mock_backend.json']);backend=MockBackend(dataset,repo,KnowledgeBase(dataset))
    with pytest.raises(BackendError):backend.execute('calc_casco_price',{**PARAMETERS['calc_casco_price'],'franchise':13},'bad','test')
    with repo.connect() as db:assert db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==0
