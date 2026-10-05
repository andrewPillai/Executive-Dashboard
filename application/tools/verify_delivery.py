"""Independent read-only delivery checks for the review artifacts."""
import json, sqlite3, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
data = json.loads((root/'data/dashboard.json').read_text())
con = sqlite3.connect('file:'+str(root/'data/northstar.sqlite')+'?mode=ro', uri=True)
def scalar(sql):
    return con.execute(sql).fetchone()[0]
checks = {
    'customers_100k': scalar('select count(*) from customers') == 100000,
    'products_100k': scalar('select count(*) from products') == 100000,
    'warehouse_US_20': scalar("select count(*) from warehouses where region='USA'") == 20,
    'warehouse_EU_7': scalar("select count(*) from warehouses where region='EU'") == 7,
    'all_audiences_100k': len(data['roles']) == 8 and all(r['recordCount'] >= 100000 for r in data['roles']),
    'six_cases': len(data['cases']) == 6,
    'three_direct_cases': sum(c['id'].startswith('DIRECT') for c in data['cases']) == 3,
    'twelve_historical_months': len(data['monthly']) == 12,
    'invoice_total_matches_summary': scalar('select sum(revenue_cents) from invoice_lines') == data['metrics']['recognizedRevenueCents'],
    'foreign_keys': not con.execute('pragma foreign_key_check').fetchmany(1),
    'service_chronology': scalar('select count(*) from service_events s join order_lines l on s.order_line_id=l.id join orders o on l.order_id=o.id where s.event_date<o.order_date') == 0,
}
for m in data['monthly']:
    actual = con.execute('select coalesce(sum(revenue_cents),0) from invoice_lines where substr(invoice_date,1,7)=?', (m['month'],)).fetchone()[0]
    checks['invoice_month_'+m['month']] = actual == m['recognizedRevenueCents']
result = {'passed': all(checks.values()), 'checks':checks, 'record_total':sum(data['counts'].values()), 'database_bytes':(root/'data/northstar.sqlite').stat().st_size}
print(json.dumps(result,indent=2))
assert result['passed'], result
