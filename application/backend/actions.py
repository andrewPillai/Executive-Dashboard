"""Local demonstration task execution, separate from immutable business facts."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field


class ProgressRequest(BaseModel):
    run_id: str
    expected_version: int = Field(ge=0)
    task_id: str
    status: Literal['In progress', 'Waiting', 'Completed']
    note: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(default='', max_length=2000)


class ResolveRequest(BaseModel):
    run_id: str
    expected_version: int = Field(ge=0)
    evidence: str = Field(min_length=10, max_length=3000)


class DiscardRequest(BaseModel):
    run_id: str
    expected_version: int = Field(ge=0)


def tasks_for(item, owner, due_date):
    actions = {
        'SUPPLY-001': [('Planning & Sourcing', 'Obtain supplier receipt and quantity confirmation'), ('Operations', 'Review receipt and fulfillment feasibility'), ('Customer Service', 'Record the customer commitment and follow-up')],
        'MARGIN-002': [('Commercial Excellence', 'Review applicable pricing and authorization'), ('Sales', 'Draft future quote treatment with customer context'), ('Finance', 'Reconcile modeled margin and record review outcome')],
        'STOCK-003': [('Operations', 'Verify available stock and proposed transfer feasibility'), ('Planning & Sourcing', 'Confirm transfer quantities and timing'), ('Customer Service', 'Record the proposed delivery update')],
        'DIRECT-004': [('Planning & Sourcing', 'Request manufacturer quantity and delivery confirmation'), ('Sales', 'Review the effect on the customer commitment'), ('Customer Service', 'Record the customer update and next checkpoint')],
        'DIRECT-005': [('Customer Service', 'Confirm outstanding quantity and request a remainder date'), ('Planning & Sourcing', 'Review manufacturer remainder confirmation'), ('Sales', 'Record the agreed customer follow-up')],
        'DIRECT-006': [('Finance', 'Reconcile supplier invoice quantity against proof of delivery'), ('Planning & Sourcing', 'Record supplier response to the discrepancy'), ('Finance', 'Document proposed correction and reconciliation outcome')],
    }
    sequence = actions.get(item['id'], [(owner, item['recommendation']), (owner, 'Review response evidence')])
    return [dict(id=str(i+1), owner=department, title=title, due_date=due_date,
                 status='Assigned', depends_on=[] if i==0 else [str(i)], note='', evidence='')
            for i,(department,title) in enumerate(sequence)]


def register_actions(app, workflow, check_version, store, case_seed):
    @app.post('/api/cases/{case_id}/discard')
    def discard(case_id: str, request: DiscardRequest):
        case_seed(case_id)
        with workflow() as db:
            current=check_version(db, case_id, request)
            if current.get('assignment') or not current.get('plan'):
                raise HTTPException(409, 'Only an unapproved draft can be discarded.')
            current.update(version=current['version']+1, status='Awaiting review', plan=None)
            store(db, case_id, current)
            return current

    def checked(db, case_id, request):
        case_seed(case_id)
        current = check_version(db, case_id, request)
        if not current.get('assignment'):
            raise HTTPException(409, 'Approve a response before tracking execution.')
        if current.get('resolution'):
            raise HTTPException(409, 'This demo case is already resolved.')
        return current

    def event(current, action, note):
        current.setdefault('history', []).append(dict(at=datetime.now(timezone.utc).isoformat(), action=action, note=note, actor='Demo human reviewer'))
        current['version'] += 1

    @app.post('/api/cases/{case_id}/progress')
    def progress(case_id: str, request: ProgressRequest):
        if not request.note.strip():
            raise HTTPException(422, 'Describe the progress update.')
        with workflow() as db:
            current = checked(db, case_id, request)
            tasks = current.get('tasks', [])
            task = next((t for t in tasks if t['id']==request.task_id), None)
            if task is None:
                raise HTTPException(404, 'Unknown task. Legacy assignments need a new demo run.')
            if task['status']=='Completed':
                raise HTTPException(409, 'Completed evidence is locked for this demo run.')
            if any(t['id'] in task['depends_on'] and t['status']!='Completed' for t in tasks):
                raise HTTPException(409, 'Complete the prerequisite task first.')
            if request.status=='Completed' and len(request.evidence.strip())<10:
                raise HTTPException(422, 'Completion requires a descriptive demo evidence reference (at least 10 characters).')
            task.update(status=request.status, note=request.note.strip(), evidence=request.evidence.strip())
            current['status']='Awaiting resolution review' if all(t['status']=='Completed' for t in tasks) else 'In progress'
            current['assignment']['status']=current['status']
            event(current, f'Task {task["id"]}: {request.status}', request.note.strip())
            store(db, case_id, current)
            return current

    @app.post('/api/cases/{case_id}/resolve')
    def resolve(case_id: str, request: ResolveRequest):
        if len(request.evidence.strip())<10:
            raise HTTPException(422, 'Describe the simulated resolution evidence.')
        with workflow() as db:
            current = checked(db, case_id, request)
            if not current.get('tasks') or any(t['status']!='Completed' for t in current['tasks']):
                raise HTTPException(409, 'Complete all coordinated tasks before resolution review.')
            current['resolution']={'evidence':request.evidence.strip(), 'mode':'simulated', 'reviewed_by':'Demo human reviewer'}
            current['status']='Resolved · simulated'
            current['assignment']['status']=current['status']
            event(current, 'Simulated resolution approved', request.evidence.strip())
            store(db, case_id, current)
            return current
