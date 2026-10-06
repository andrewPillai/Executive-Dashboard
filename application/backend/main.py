"""Local synthetic demo API. No enterprise authentication or live AI is claimed."""
import json
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import actions
from . import reads
from . import depth
from . import cohorts
from . import questioning
from .db import open_business
register_actions = actions.register_actions
tasks_for = actions.tasks_for

ROOT = Path(__file__).resolve().parents[1]


class DraftRequest(BaseModel):
    run_id: str
    expected_version: int = Field(ge=0)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: date | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=2000)


class ApprovalRequest(BaseModel):
    run_id: str
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=160)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


def create_app(data_dir=None, workflow_path=None, frontend_dir=None):
    data_dir = Path(data_dir or ROOT / 'data')
    workflow_path = Path(workflow_path or Path(__file__).parent / 'workflow.sqlite')
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title='Northstar synthetic operations demo')

    @contextmanager
    def workflow():
        db = sqlite3.connect(workflow_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    with workflow() as db:
        db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS approvals (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('run_id', str(uuid.uuid4())))

    def seed():
        return json.loads((data_dir / 'dashboard.json').read_text())

    def case_seed(case_id):
        item = next((x for x in seed()['cases'] if x['id'] == case_id), None)
        if item is None:
            raise HTTPException(404, 'Unknown case')
        return item

    def run(db):
        return db.execute("SELECT value FROM metadata WHERE key='run_id'").fetchone()[0]

    def state(db, case_id):
        row = db.execute('SELECT payload FROM cases WHERE id=?', (case_id,)).fetchone()
        return json.loads(row[0]) if row else dict(version=0, status='Awaiting review', plan=None, assignment=None)

    def store(db, case_id, value):
        db.execute('INSERT OR REPLACE INTO cases VALUES (?,?)', (case_id, json.dumps(value)))

    def check_version(db, case_id, request):
        if request.run_id != run(db):
            raise HTTPException(409, 'Demo run changed. Refresh before acting.')
        current = state(db, case_id)
        if request.expected_version != current['version']:
            raise HTTPException(409, 'Plan changed. Refresh and review the current version.')
        return current

    def order_query(q='', page=1, page_size=25, case_id=None, sort='id', direction='asc', customer_id=None, product_id=None, manufacturer_id=None, internal_where=None):
        allowed = {'id': 'l.id', 'order_date': 'o.order_date', 'customer': 'cu.name', 'product': 'p.name', 'quantity': 'l.ordered_qty'}
        if sort not in allowed or direction not in ('asc', 'desc'):
            raise HTTPException(422, 'Unsupported sort or direction')
        where, args = [], []
        for column, value in [('o.customer_id', customer_id), ('l.product_id', product_id), ('p.manufacturer_id', manufacturer_id)]:
            if value is not None:
                where.append(column + '=?')
                args.append(value)
        if internal_where:
            where.append('(' + internal_where + ')')
        if q:
            where.append('(cu.name LIKE ? OR p.name LIKE ? OR p.sku LIKE ? OR CAST(o.id AS TEXT)=?)')
            args += ['%' + q + '%'] * 3 + [q]
        if case_id:
            case_seed(case_id)
            where.append('l.scenario_id=?')
            args.append(case_id)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        joins = ''' FROM order_lines l JOIN orders o ON o.id=l.order_id
            JOIN customers cu ON cu.id=o.customer_id JOIN products p ON p.id=l.product_id
            LEFT JOIN manufacturers m ON m.id=p.manufacturer_id
            LEFT JOIN warehouses w ON w.id=l.warehouse_id
            LEFT JOIN suppliers s ON s.id=p.supplier_id
            LEFT JOIN direct_fulfillment df ON df.order_line_id=l.id'''
        fields = '''l.id,l.order_id,o.order_date,cu.id customer_id,cu.name customer_name,
            o.region,p.id product_id,p.name product_name,p.sku,m.id manufacturer_id,m.name manufacturer_name,
            s.id supplier_id,s.name supplier_name,w.id warehouse_id,w.name warehouse_name,l.fulfillment_mode,l.ordered_qty,
            l.shipped_qty,l.unit_price_cents,l.unit_cost_cents,l.requested_date,
            l.original_committed_date,l.shipped_date,l.delivered_qty,l.delivered_date,l.scenario_id,
            df.po_reference,df.confirmation_status,df.proof_of_delivery,df.supplier_invoice_qty,
            (l.ordered_qty-l.shipped_qty)*l.unit_price_cents open_value_cents'''
        with open_business(data_dir) as db:
            total = db.execute('SELECT count(*)' + joins + clause, args).fetchone()[0]
            rows = db.execute('SELECT ' + fields + joins + clause + f' ORDER BY {allowed[sort]} {direction}, l.id ASC LIMIT ? OFFSET ?', args + [page_size, (page - 1) * page_size]).fetchall()
            return dict(items=reads.enrich_orders(db, [dict(x) for x in rows], seed()['asOf']), total=total, page=page, page_size=page_size)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'synthetic': True, 'data_source': 'postgresql' if __import__('os').getenv('DATABASE_URL') else 'sqlite fallback', 'ai_mode': 'controlled query catalog', 'ai_rpm_limit': questioning.AI_RPM_LIMIT, 'authentication': 'local demo only'}

    @app.post('/api/ask')
    def ask(request: QuestionRequest):
        try:
            return questioning.answer(request.question, data_dir)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except questioning.AIRateLimitError as exc:
            raise HTTPException(429, str(exc))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

    @app.post('/api/ask/advanced')
    def ask_advanced(request: QuestionRequest):
        try:
            return questioning.advanced_answer(request.question, data_dir)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except questioning.AIRateLimitError as exc:
            raise HTTPException(429, str(exc))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

    @app.get('/api/bootstrap')
    def bootstrap():
        result = seed()
        with workflow() as db:
            result['workflow'] = {'run_id': run(db), 'cases': {x['id']: state(db, x['id']) for x in result['cases']}}
        return result

    @app.get('/api/orders')
    def orders(q: str = Query('', max_length=200), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), case_id: str | None = None, sort: str = 'id', direction: str = 'asc', customer_id: int | None = Query(None, ge=1), product_id: int | None = Query(None, ge=1), manufacturer_id: int | None = Query(None, ge=1), department: str | None = None):
        if department is not None and department not in cohorts.COHORTS:
            raise HTTPException(422, 'Unknown department cohort')
        return order_query(q, page, page_size, case_id, sort, direction, customer_id, product_id, manufacturer_id, cohorts.COHORTS[department][0] if department else None)

    records_query = reads.register_reads(app, data_dir, seed)
    depth.register_depth(app, data_dir, seed, order_query, records_query)

    @app.get('/api/cases')
    def cases():
        with workflow() as db:
            return {'run_id': run(db), 'items': [{**x, 'workflow': state(db, x['id'])} for x in seed()['cases']]}

    @app.get('/api/cases/{case_id}')
    def case_detail(case_id: str):
        item = case_seed(case_id)
        evidence = order_query(case_id=case_id, page_size=100)
        with workflow() as db:
            return {**item, 'run_id': run(db), 'workflow': state(db, case_id), 'evidenceRows': evidence['items'], 'evidenceTotal': evidence['total']}

    @app.post('/api/cases/{case_id}/draft')
    def draft(case_id: str, request: DraftRequest):
        item = case_seed(case_id)
        if request.summary is not None and not request.summary.strip():
            raise HTTPException(422, 'Draft summary cannot be blank.')
        with workflow() as db:
            current = check_version(db, case_id, request)
            if current['assignment']:
                raise HTTPException(409, 'This case already has an approved assignment. Reset the demo to start again.')
            current.update(version=current['version'] + 1, status='Draft ready')
            current['plan'] = {'owner': request.owner or item['owner'], 'due_date': str(request.due_date) if request.due_date else None,
                               'summary': request.summary.strip() if request.summary else item['recommendation'], 'steps': [request.summary.strip() if request.summary else item['recommendation'], 'Review source evidence with affected departments.', 'Record outcome and report progress.'], 'mode': 'human revised' if request.summary else 'scripted', 'version': current['version']}
            current['plan']['proposed_tasks'] = tasks_for(item, current['plan']['owner'], current['plan']['due_date'])
            store(db, case_id, current)
            return {**current, 'run_id': run(db)}

    @app.post('/api/cases/{case_id}/approve')
    def approve(case_id: str, request: ApprovalRequest):
        case_seed(case_id)
        with workflow() as db:
            if request.run_id != run(db):
                raise HTTPException(409, 'Demo run changed. Refresh before acting.')
            key = request.run_id + ':' + request.idempotency_key
            fingerprint = json.dumps([case_id, request.expected_version])
            prior = db.execute('SELECT fingerprint,response FROM approvals WHERE key=?', (key,)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise HTTPException(409, 'Idempotency key already used for a different approval.')
                return json.loads(prior['response'])
            current = check_version(db, case_id, request)
            if not current['plan'] or current['assignment']:
                raise HTTPException(409, 'Review a new draft before approval.')
            current['assignment'] = {'id': str(uuid.uuid4()), 'owner': current['plan']['owner'], 'due_date': current['plan']['due_date'], 'approved_plan_version': current['version'], 'approved_by': 'Demo human reviewer', 'status': 'Assigned'}
            current['tasks'] = current['plan'].get('proposed_tasks', tasks_for(case_seed(case_id), current['plan']['owner'], current['plan']['due_date']))
            current.update(version=current['version'] + 1, status='Assigned')
            store(db, case_id, current)
            response = {**current, 'run_id': run(db)}
            db.execute('INSERT INTO approvals VALUES (?,?,?)', (key, fingerprint, json.dumps(response)))
            return response

    @app.post('/api/reset')
    def reset():
        with workflow() as db:
            new_run = str(uuid.uuid4())
            db.execute('UPDATE metadata SET value=? WHERE key=?', (new_run, 'run_id'))
            db.execute('DELETE FROM cases')
            db.execute('DELETE FROM approvals')
            return {'run_id': new_run}

    register_actions(app, workflow, check_version, store, case_seed)

    dist = Path(frontend_dir or ROOT / 'frontend' / 'dist')
    if dist.is_dir():
        @app.get('/', include_in_schema=False)
        def frontend_root():
            # The entrypoint must be revalidated after a deployment so the browser
            # does not keep an older hashed JavaScript bundle.
            return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-store, max-age=0'})

        class SPAFiles(StaticFiles):
            async def get_response(self, path, scope):
                try:
                    response = await super().get_response(path, scope)
                    if response.status_code == 404 and not path.startswith(('api/', 'assets/')) and '.' not in path:
                        return FileResponse(dist / 'index.html')
                    return response
                except Exception as exc:
                    if getattr(exc, 'status_code', None) == 404 and not path.startswith(('api/', 'assets/')) and '.' not in path:
                        return FileResponse(dist / 'index.html')
                    raise
        app.mount('/', SPAFiles(directory=dist, html=True), name='frontend')
    return app


app = create_app()
