from fastapi.testclient import TestClient
from backend.main import create_app


def test_revision_discard_and_stale_approval(tmp_path):
    client=TestClient(create_app(workflow_path=tmp_path/'revision.sqlite'))
    run=client.get('/api/bootstrap').json()['workflow']['run_id']
    base='/api/cases/DIRECT-004'
    client.post(base+'/draft',json=dict(run_id=run,expected_version=0))
    changed=client.post(base+'/draft',json=dict(run_id=run,expected_version=1,summary='Request a remainder confirmation before updating the customer',owner='Sales',due_date='2026-10-03')).json()
    assert changed['plan']['mode']=='human revised'
    assert changed['plan']['owner']=='Sales'
    assert changed['plan']['proposed_tasks'][0]['due_date']=='2026-10-03'
    assert client.post(base+'/approve',json=dict(run_id=run,expected_version=1,idempotency_key='stale')).status_code==409
    discarded=client.post(base+'/discard',json=dict(run_id=run,expected_version=2)).json()
    assert discarded['plan'] is None
    assert discarded['status']=='Awaiting review'
    assert client.post(base+'/approve',json=dict(run_id=run,expected_version=3,idempotency_key='discarded')).status_code==409


def test_execution_requires_approval_dependencies_evidence_and_resolution(tmp_path):
    client=TestClient(create_app(workflow_path=tmp_path/'actions.sqlite'))
    run=client.get('/api/bootstrap').json()['workflow']['run_id']
    base='/api/cases/DIRECT-005'
    before=client.get(base).json()['evidenceRows']
    def body(version, **extra): return dict(run_id=run,expected_version=version,**extra)
    assert client.post(base+'/progress',json=body(0,task_id='1',status='In progress',note='Review')).status_code==409
    draft=client.post(base+'/draft',json=body(0,owner='Customer Service',due_date='2026-10-02')).json()
    assert len(draft['plan']['proposed_tasks'])==3
    approved=client.post(base+'/approve',json=body(1,idempotency_key='test')).json()
    assert approved['tasks']==draft['plan']['proposed_tasks']
    assert client.post(base+'/progress',json=body(2,task_id='2',status='Completed',note='Done',evidence='Synthetic evidence')).status_code==409
    assert client.post(base+'/resolve',json=body(2,evidence='Synthetic receipt')).status_code==409
    assert client.post(base+'/progress',json=body(2,task_id='1',status='Completed',note='Done')).status_code==422
    v=2
    for task in approved['tasks']:
        response=client.post(base+'/progress',json=body(v,task_id=task['id'],status='Completed',note='Reviewed synthetic outcome',evidence='Demo receipt reference '+task['id']))
        assert response.status_code==200
        v=response.json()['version']
    assert response.json()['status']=='Awaiting resolution review'
    assert client.post(base+'/resolve',json=body(2,evidence='Stale resolution evidence')).status_code==409
    resolved=client.post(base+'/resolve',json=body(v,evidence='Synthetic receipt and customer confirmation reviewed'))
    assert resolved.status_code==200
    assert resolved.json()['status']=='Resolved · simulated'
    assert len(resolved.json()['history'])==4
    assert client.get(base).json()['evidenceRows']==before
    assert client.post(base+'/progress',json=body(v+1,task_id='1',status='In progress',note='Reopen')).status_code==409
