from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(workflow_path=tmp_path / 'workflow.sqlite'))


def context(client):
    body = client.get('/api/bootstrap').json()
    return body['workflow']['run_id'], body['cases'][0]['id']


def test_approval_requires_draft_and_rejects_stale_plan(client):
    run, case = context(client)
    url = f'/api/cases/{case}'
    assert client.post(url + '/approve', json=dict(run_id=run, expected_version=0, idempotency_key='early')).status_code == 409
    assert client.post(url + '/draft', json=dict(run_id=run, expected_version=0)).json()['version'] == 1
    assert client.post(url + '/draft', json=dict(run_id=run, expected_version=1, owner='Operations')).json()['version'] == 2
    assert client.post(url + '/approve', json=dict(run_id=run, expected_version=1, idempotency_key='stale')).status_code == 409
    payload = dict(run_id=run, expected_version=2, idempotency_key='once')
    approved = client.post(url + '/approve', json=payload)
    assert approved.status_code == 200
    assert approved.json()['assignment']['owner'] == 'Operations'
    assert client.post(url + '/approve', json=payload).json() == approved.json()
    assert client.get(url).json()['workflow']['version'] == 3
    assert client.post(url + '/approve', json={**payload, 'expected_version': 3}).status_code == 409


def test_reset_invalidates_previous_run_and_preserves_business_data(client):
    run, case = context(client)
    total = client.get('/api/orders').json()['total']
    client.post(f'/api/cases/{case}/draft', json=dict(run_id=run, expected_version=0))
    new = client.post('/api/reset').json()['run_id']
    assert new != run
    assert client.post(f'/api/cases/{case}/approve', json=dict(run_id=run, expected_version=1, idempotency_key='old')).status_code == 409
    assert client.get(f'/api/cases/{case}').json()['workflow']['plan'] is None
    assert client.get('/api/orders').json()['total'] == total


def test_search_pagination_and_evidence(client):
    _, case = context(client)
    first = client.get('/api/orders', params={'page_size': 2}).json()
    second = client.get('/api/orders', params={'page_size': 2, 'page': 2}).json()
    assert first['total'] >= 100000
    assert {x['id'] for x in first['items']}.isdisjoint(x['id'] for x in second['items'])
    assert client.get('/api/orders', params={'q': "' OR 1=1 --"}).json()['items'] == []
    assert client.get('/api/orders', params={'sort': 'id; DROP TABLE orders'}).status_code == 422
    assert client.get('/api/orders', params={'page_size': 100000}).status_code == 422
    evidence = client.get(f'/api/cases/{case}').json()['evidenceRows']
    assert evidence and all(x['scenario_id'] == case for x in evidence)
    assert client.get('/api/cases/missing').status_code == 404


def test_workflow_survives_application_restart(tmp_path):
    path = tmp_path / 'persist.sqlite'
    client = TestClient(create_app(workflow_path=path))
    run, case = context(client)
    client.post(f'/api/cases/{case}/draft', json=dict(run_id=run, expected_version=0))
    restarted = TestClient(create_app(workflow_path=path))
    result = restarted.get(f'/api/cases/{case}').json()
    assert result['run_id'] == run
    assert result['workflow']['version'] == 1


def test_direct_delivery_and_invoice_evidence(client):
    partial = client.get('/api/cases/DIRECT-005').json()['evidenceRows'][0]
    assert partial['ordered_qty'] == 68
    assert partial['delivered_qty'] == 34
    assert partial['delivered_date'] == '2026-09-24'
    assert partial['warehouse_name'] is None
    assert partial['confirmation_status'] == 'Confirmed'
    assert partial['proof_of_delivery']
    discrepancy = client.get('/api/orders', params={'case_id': 'DIRECT-006'}).json()['items'][0]
    assert discrepancy['supplier_invoice_qty'] - discrepancy['delivered_qty'] == 2
    assert discrepancy['po_reference'] == 'DPO-299973'


def test_entity_scope_and_reconciliation(client):
    result = client.get('/api/entities/products/99972').json()
    rows = client.get('/api/orders', params={'product_id': 99972, 'page_size': 100}).json()
    assert rows['total'] == len(rows['items'])
    assert all(x['product_id'] == 99972 for x in result['orders']['items'])
    values = {x['key']: x['value'] for x in result['metrics']}
    assert values['order_lines'] == rows['total']
    assert values['bookings'] == sum(x['ordered_qty'] * x['unit_price_cents'] for x in rows['items'])
    assert values['invoiced_sales'] == sum(x['shipped_qty'] * x['unit_price_cents'] for x in rows['items'])
    customer = client.get('/api/entities/customers/49986').json()
    assert {x['id'] for x in customer['cases']} == {'DIRECT-004', 'DIRECT-005'}
    assert all(x['customer_id'] == 49986 for x in customer['orders']['items'])
    manufacturer = client.get('/api/entities/manufacturers/472').json()
    assert all(x['manufacturer_id'] == 472 for x in manufacturer['orders']['items'])
    inventory = client.get('/api/entities/products/99995').json()['inventory']
    assert {x['on_hand_qty'] for x in inventory} == {0, 500}
    assert client.get('/api/entities/customers/9999999').status_code == 404
    assert client.get('/api/entities/orders/1').status_code == 404


def test_department_metrics_and_queue_scope(client):
    responses = {role: client.get('/api/departments/' + role) for role in ['executive','sales','commercial','service','operations','planning','finance','analytics']}
    assert all(x.status_code == 200 for x in responses.values())
    for response in responses.values():
        body = response.json()
        assert len(body['metrics']) == 3
        assert len(body['queue']['items']) <= 10
        assert all(x['definition'] for x in body['metrics'])
    ops = responses['operations'].json()
    assert all(x['fulfillment_mode'] == 'STOCK' and x['shipped_qty'] < x['ordered_qty'] for x in ops['queue']['items'])
    executive = {x['key']:x['value'] for x in responses['executive'].json()['metrics']}
    finance = {x['key']:x['value'] for x in responses['finance'].json()['metrics']}
    assert executive['invoiced_sales'] == finance['invoiced_sales']
    import sqlite3
    with sqlite3.connect('file:' + str(Path(__file__).resolve().parents[1] / 'data/northstar.sqlite') + '?mode=ro', uri=True) as db:
        assert executive['invoiced_sales'] == db.execute('SELECT sum(revenue_cents) FROM invoice_lines').fetchone()[0]
    assert client.get('/api/departments/not-a-role').status_code == 404
