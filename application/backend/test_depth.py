import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(workflow_path=tmp_path/'workflow.sqlite'))


def test_department_cohort_full_navigation(client):
    for role in ('executive','sales','commercial','service','operations','planning','finance','analytics'):
        queue=client.get('/api/departments/'+role).json()['queue']
        full=client.get('/api/orders',params={'department':role,'page_size':10,'sort':'order_date','direction':'desc'}).json()
        assert queue['total']==full['total']
        assert [x['id'] for x in queue['items']]==[x['id'] for x in full['items']]
        assert queue['scope']=={'department':role}
    commercial=client.get('/api/departments/commercial').json()
    assert next(x['value'] for x in commercial['metrics'] if x['key']=='below_floor')==commercial['queue']['total']
    assert all(x['unit_price_cents']<x['floor_price_cents'] for x in commercial['queue']['items'])
    # OR branches must remain grouped when an entity filter is supplied.
    scoped=client.get('/api/orders',params={'department':'finance','product_id':99989}).json()['items']
    assert scoped and all(x['product_id']==99989 for x in scoped)
    assert client.get('/api/orders',params={'department':'invalid'}).status_code==422


def test_sources_and_supply_context(client):
    for kind,params in [('service',{'customer_id':49986}),('purchases',{'product_id':99981}),('quotes',{'customer_id':49986})]:
        result=client.get('/api/records/'+kind,params=params).json()
        assert result['items']
        for key,value in params.items():
            assert all(x[key]==value for x in result['items'])
    service=client.get('/api/records/service',params={'status':'Open'}).json()
    department=client.get('/api/departments/service').json()
    assert service['total']==next(x['value'] for x in department['metrics'] if x['key']=='open_events')
    assert client.get('/api/records/purchases',params={'customer_id':1}).status_code==422
    assert client.get('/api/records/quotes',params={'status':"' OR 1=1 --"}).json()['total']==0
    entity=client.get('/api/entities/products/99981').json()
    assert entity['sourceContext']['purchases']['items'][0]['product_id']==99981
    planning=client.get('/api/orders',params={'department':'planning'}).json()['items']
    with sqlite3.connect('file:'+str(Path(__file__).resolve().parents[1]/'data/northstar.sqlite')+'?mode=ro',uri=True) as db:
        for line in planning:
            if line['candidate_po_id']:
                pair=db.execute('SELECT product_id,warehouse_id FROM purchase_lines WHERE id=?',(line['candidate_po_id'],)).fetchone()
                assert pair==(line['product_id'],line['warehouse_id'])
            else:
                assert line['confirmation_status']=='Pending'


def test_reporting_reconciliation_and_comparison(client):
    totals={}
    for period in ('all','2026-09','2026-10'):
        for region in ('all','USA','EU'):
            body=client.get('/api/reports',params={'period':period,'region':region}).json()
            metrics={x['key']:x['value'] for x in body['metrics']}
            assert metrics['invoiced_sales']==sum(x['invoiced_sales_cents'] for x in body['monthly'])
            assert metrics['gross_profit']==sum(x['gross_profit_cents'] for x in body['monthly'])
            totals[period,region]=metrics['invoiced_sales']
        assert totals[period,'all']==totals[period,'USA']+totals[period,'EU']
    october=client.get('/api/reports',params={'period':'2026-10'}).json()
    assert october['previous']['comparison']=='Same elapsed calendar days of prior month'
    with sqlite3.connect('file:'+str(Path(__file__).resolve().parents[1]/'data/northstar.sqlite')+'?mode=ro',uri=True) as db:
        expected=db.execute("SELECT sum(revenue_cents) FROM invoice_lines WHERE invoice_date='2026-09-01'").fetchone()[0]
        assert october['previous']['invoiced_sales_cents']==expected
    assert client.get('/api/reports',params={'period':"' OR 1=1"}).status_code==422


def test_delivery_cohort_source_sort_and_operational_series(client):
    sales=client.get('/api/orders',params={'department':'sales','page_size':100}).json()
    assert all(x['delivered_qty']<x['ordered_qty'] for x in sales['items'])
    with sqlite3.connect('file:'+str(Path(__file__).resolve().parents[1]/'data/northstar.sqlite')+'?mode=ro',uri=True) as db:
        assert sales['total']==db.execute('SELECT count(*) FROM order_lines WHERE delivered_qty<ordered_qty').fetchone()[0]
    oldest=client.get('/api/records/purchases',params={'open_only':True,'sort':'oldest'}).json()
    assert oldest['items'] and all(x['open_qty']>0 for x in oldest['items'])
    dates=[x['expected_date'] for x in oldest['items']]
    assert dates==sorted(dates)
    newest=client.get('/api/records/service',params={'sort':'newest'}).json()['items']
    assert [x['event_date'] for x in newest]==sorted([x['event_date'] for x in newest],reverse=True)
    assert client.get('/api/records/quotes',params={'open_only':True}).status_code==422
    report=client.get('/api/reports').json()['operationalMonthly']
    eligible=sum(x['eligible_lines'] for x in report)
    successes=sum(x['otif_lines'] for x in report)
    baseline=client.get('/api/bootstrap').json()['metrics']['otifPercent']
    assert round(100*successes/eligible,2)==baseline
    regions=[client.get('/api/reports',params={'region':r}).json()['operationalMonthly'] for r in ['USA','EU']]
    assert eligible==sum(x['eligible_lines'] for rows in regions for x in rows)
    assert client.get('/api/reports',params={'period':'2026-10'}).json()['operationalMonthly']==[]
