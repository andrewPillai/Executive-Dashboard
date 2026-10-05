#!/usr/bin/env python3
"""Deterministic synthetic business generator; no production data or dependencies."""
import sqlite3,json,datetime,random,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]; OUT=ROOT/'data'; OUT.mkdir(exist_ok=True)
DB=OUT/'northstar.sqlite'; DB.unlink(missing_ok=True)
r=random.Random(417); start=datetime.date(2025,10,1); today=datetime.date(2026,10,1)
c=sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=ON')
c.executescript('''
CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,region TEXT,segment TEXT);
CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT,country TEXT);
CREATE TABLE warehouses(id INTEGER PRIMARY KEY,name TEXT,region TEXT,country TEXT);
CREATE TABLE manufacturers(id INTEGER PRIMARY KEY,name TEXT);
CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE,name TEXT,category TEXT,supplier_id INTEGER REFERENCES suppliers(id),unit_cost_cents INTEGER,list_price_cents INTEGER,manufacturer_id INTEGER REFERENCES manufacturers(id));
CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),order_date TEXT,region TEXT);
CREATE TABLE order_lines(id INTEGER PRIMARY KEY,order_id INTEGER REFERENCES orders(id),product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),ordered_qty INTEGER,shipped_qty INTEGER,unit_price_cents INTEGER,unit_cost_cents INTEGER,requested_date TEXT,original_committed_date TEXT,shipped_date TEXT,scenario_id TEXT,fulfillment_mode TEXT,ship_from_supplier_id INTEGER REFERENCES suppliers(id),ship_from_manufacturer_id INTEGER REFERENCES manufacturers(id));
CREATE TABLE invoice_lines(id INTEGER PRIMARY KEY,order_line_id INTEGER REFERENCES order_lines(id),invoice_date TEXT,quantity INTEGER,revenue_cents INTEGER,cost_cents INTEGER);
CREATE TABLE purchase_lines(id INTEGER PRIMARY KEY,supplier_id INTEGER REFERENCES suppliers(id),product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),ordered_qty INTEGER,received_qty INTEGER,po_date TEXT,expected_date TEXT,receipt_date TEXT);
CREATE TABLE inventory_movements(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),movement_date TEXT,kind TEXT,quantity INTEGER,order_line_id INTEGER REFERENCES order_lines(id),purchase_line_id INTEGER REFERENCES purchase_lines(id));
CREATE TABLE inventory_balances(product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),opening_qty INTEGER,on_hand_qty INTEGER,PRIMARY KEY(product_id,warehouse_id));
CREATE TABLE quote_lines(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),product_id INTEGER REFERENCES products(id),quote_date TEXT,quantity INTEGER,unit_price_cents INTEGER,status TEXT);
CREATE TABLE service_events(id INTEGER PRIMARY KEY,order_line_id INTEGER REFERENCES order_lines(id),event_date TEXT,category TEXT,status TEXT);
CREATE TABLE pricing_records(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),effective_date TEXT,list_price_cents INTEGER,floor_price_cents INTEGER);
''')
c.executemany('INSERT INTO manufacturers VALUES(?,?)',((i,f'Fictional Manufacturer {i:04}') for i in range(1,501)))
regions=['USA','EU']; cats=['Laboratory chemicals','Consumables','Bioprocess supplies','Instruments','Safety supplies']
c.executemany('INSERT INTO customers VALUES(?,?,?,?)',((i,f'Fictional Research Customer {i:06}',regions[i%2],['Biopharma','Education','Industrial','Healthcare'][i%4]) for i in range(1,100001)))
c.executemany('INSERT INTO suppliers VALUES(?,?,?)',((i,f'Fictional Supplier {i:04}', ['US','DE','SG'][i%3]) for i in range(1,3001)))
cities=['Boston','Atlanta','Chicago','Dallas','Denver','Los Angeles','Seattle','Portland','Phoenix','Salt Lake City','Minneapolis','St Louis','Kansas City','Houston','Miami','Charlotte','Nashville','Columbus','Philadelphia','Newark','Frankfurt, Germany','Paris, France','Rotterdam, Netherlands','Antwerp, Belgium','Dublin, Ireland','Madrid, Spain','Warsaw, Poland']
c.executemany('INSERT INTO warehouses VALUES(?,?,?,?)',((i,'Fictional '+city+' Distribution Center','USA' if i<=20 else 'EU','USA' if i<=20 else city.split(', ')[1]) for i,city in enumerate(cities,1)))
products={}
for i in range(1,100001):
    cost=6000+(i*7919)%60000; price=cost*145//100
    products[i]=(cost,price)
c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?,?,?)',((i,f'NS-{i:06}',f'{cats[i%5]} item {i:06}',cats[i%5],(i-1)%3000+1,*products[i],(i-1)%500+1) for i in products))
c.executemany('INSERT INTO pricing_records VALUES(?,?,?,?,?)',((i,i,str(start),products[i][1],products[i][0]*110//100) for i in products))
orders=[]
for i in range(1,150001):
    d=start+datetime.timedelta(days=(i-1)%365)
    if i>149980:d=datetime.date(2026,9,20)
    orders.append((i,(i-1)%100000+1,str(d),regions[i%2]))
c.executemany('INSERT INTO orders VALUES(?,?,?,?)',orders)
lines=[]; invoices=[]; moves=[]; balances={}; movement_id=0
for i in range(1,300001):
    oid=(i+1)//2; p=(i-1)%100000+1; w=(p-1)%27+1; cost,price=products[p]; qty=10+(i*7)%71
    d=datetime.date.fromisoformat(orders[oid-1][2]); qty=max(1,round(qty*[0.86,0.92,1.0,0.97,1.02,1.06,0.94,0.95,1.14,1.01,1.08,1.05][d.month-1])); due=d+datetime.timedelta(days=5); committed=due+datetime.timedelta(days=1)
    ship=due+datetime.timedelta(days=2 if i%11==0 else -3); shipped=qty if ship<=today else 0
    scenario=None
    if i>299980:
        scenario='SUPPLY-001' if i<=299988 else 'MARGIN-002' if i<=299994 else 'STOCK-003'
        if scenario!='MARGIN-002':shipped=0;ship=None
        else:price=cost*103//100
    mode='DIRECT' if i%10==0 and i<299980 else 'STOCK'
    if i in [299971,299972,299973]:
        mode='DIRECT';scenario={299971:'DIRECT-004',299972:'DIRECT-005',299973:'DIRECT-006'}[i]
        if i==299971:shipped=0;ship=None
        if i==299972:shipped=qty//2
    lines.append((i,oid,p,w if mode=='STOCK' else None,qty,shipped,price,cost,str(due),str(committed),str(ship) if shipped else None,scenario,mode,(p-1)%3000+1 if mode=='DIRECT' else None,(p-1)%500+1 if mode=='DIRECT' else None))
    balances.setdefault((p,w),[1000,1000])
    if shipped:
        invoices.append((i,i,str(ship),shipped,shipped*price,shipped*cost))
        if mode=='STOCK':
            movement_id+=1;moves.append((movement_id,p,w,str(ship),'SHIPMENT',-shipped,i,None));balances[(p,w)][1]-=shipped
c.executemany('INSERT INTO order_lines VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',lines)
c.executemany('INSERT INTO invoice_lines VALUES(?,?,?,?,?,?)',invoices)
pos=[]
for i in range(1,100001):
    p=i;w=(p-1)%27+1;d=start+datetime.timedelta(days=(i-1)%350); receipt=d+datetime.timedelta(days=7)
    pos.append((i,(p-1)%3000+1,p,w,100,100,str(d),str(receipt),str(receipt)))
    movement_id+=1;moves.append((movement_id,p,w,str(receipt),'RECEIPT',100,None,i));balances[(p,w)][1]+=100
# Seed real shortage and contrasting excess stock, with explicit inventory adjustments.
for line in lines[-20:]:
    i,oid,p,w,qty,shipped,price,cost,crd,occd,sd,scenario,mode,supplier,manufacturer=line
    if scenario in ['SUPPLY-001','STOCK-003']:
        adjustment=-balances[(p,w)][1];balances[(p,w)][1]=0;movement_id+=1
        moves.append((movement_id,p,w,'2026-09-19','CYCLE_COUNT_ADJUSTMENT',adjustment,None,None))
        if scenario=='STOCK-003':balances[(p,w%27+1)]=[500,500]
# Delayed POs correspond exactly to shortage products: remove previously modeled receipt.
for idx,po in enumerate(pos):
    if po[2] in range(99981,99989):
        p=po[2];w=po[3];pos[idx]=(po[0],po[1],p,w,100,0,'2026-09-10','2026-09-18',None)
        # Reverse receipt and adjust count correction to keep shortage on hand zero.
        for j,m in enumerate(moves):
            if m[7]==po[0]:moves[j]=(m[0],p,w,'2026-09-18','RECEIPT',0,None,po[0]);break
        for j in range(len(moves)-14,len(moves)):
            m=moves[j]
            if m[1]==p and m[4]=='CYCLE_COUNT_ADJUSTMENT':moves[j]=m[:5]+(m[5]+100,)+m[6:]
c.executemany('INSERT INTO purchase_lines VALUES(?,?,?,?,?,?,?,?,?)',pos)
c.executemany('INSERT INTO inventory_movements VALUES(?,?,?,?,?,?,?,?)',moves)
c.executemany('INSERT INTO inventory_balances VALUES(?,?,?,?)',((p,w,*v) for (p,w),v in balances.items()))
c.executemany('INSERT INTO quote_lines VALUES(?,?,?,?,?,?,?)',((i,(i-1)%100000+1,i,str(start+datetime.timedelta(days=(i-1)%365)),20,products[i][1],['Accepted','Open','Expired'][i%3]) for i in range(1,100001)))
c.executemany('INSERT INTO service_events VALUES(?,?,?,?,?)',((i,i*3,str(start+datetime.timedelta(days=((i*3+1)//2-1)%365)),['Order inquiry','Delivery follow-up','Documentation request','Complaint'][i%4],['Resolved','Resolved','Open'][i%3]) for i in range(1,100001)))
c.executescript('CREATE INDEX lines_order ON order_lines(order_id); CREATE INDEX movements_stock ON inventory_movements(product_id,warehouse_id); CREATE INDEX invoice_order_line ON invoice_lines(order_line_id);')
c.executescript('''ALTER TABLE order_lines ADD COLUMN delivered_date TEXT; ALTER TABLE order_lines ADD COLUMN delivered_qty INTEGER DEFAULT 0; CREATE TABLE direct_fulfillment(order_line_id INTEGER PRIMARY KEY REFERENCES order_lines(id),supplier_id INTEGER REFERENCES suppliers(id),manufacturer_id INTEGER REFERENCES manufacturers(id),po_reference TEXT,confirmation_status TEXT,ordered_qty INTEGER,shipped_qty INTEGER,delivered_qty INTEGER,proof_of_delivery TEXT,supplier_invoice_qty INTEGER);''')
c.executemany('INSERT INTO direct_fulfillment VALUES(?,?,?,?,?,?,?,?,?,?)',((l[0],l[13],l[14],f'DPO-{l[0]}','Pending' if l[11]=='DIRECT-004' else 'Confirmed',l[4],l[5],l[5],f'SYNTHETIC-POD-{l[0]}' if l[5] else None,l[5]+2 if l[11]=='DIRECT-006' else l[5]) for l in lines if l[12]=='DIRECT'))
c.execute("UPDATE order_lines SET delivered_date=date(shipped_date,'+2 days'),delivered_qty=shipped_qty WHERE shipped_date IS NOT NULL AND date(shipped_date,'+2 days')<='2026-10-01'")
c.execute("UPDATE direct_fulfillment SET delivered_qty=(SELECT delivered_qty FROM order_lines WHERE id=order_line_id),proof_of_delivery=CASE WHEN (SELECT delivered_qty FROM order_lines WHERE id=order_line_id)>0 THEN proof_of_delivery ELSE NULL END")
c.execute("UPDATE service_events SET event_date=(SELECT min(date(o.order_date,'+2 days'),'2026-10-01') FROM order_lines l JOIN orders o ON o.id=l.order_id WHERE l.id=service_events.order_line_id)")
# Compute an opening balance sufficient for nonnegative stock on every movement day.
c.execute("DELETE FROM inventory_movements WHERE kind='CYCLE_COUNT_ADJUSTMENT'")
shortages={(l[2],l[3]) for l in lines if l[11] in ['SUPPLY-001','STOCK-003']}
for (p,w),v in balances.items():
    stock=0;low=0
    for q, in c.execute('SELECT quantity FROM inventory_movements WHERE product_id=? AND warehouse_id=? ORDER BY movement_date,id',(p,w)):
        stock+=q;low=min(low,stock)
    opening=max(0,-low)+20+p%21
    if v[0]==500:opening=500
    ending=opening+stock
    if (p,w) in shortages:
        movement_id+=1;c.execute('INSERT INTO inventory_movements VALUES(?,?,?,?,?,?,?,?)',(movement_id,p,w,'2026-10-01','CYCLE_COUNT_ADJUSTMENT',-ending,None,None));ending=0
    c.execute('UPDATE inventory_balances SET opening_qty=?,on_hand_qty=? WHERE product_id=? AND warehouse_id=?',(opening,ending,p,w))
c.commit()
def scalar(q):return c.execute(q).fetchone()[0]
counts={t:scalar('SELECT count(*) FROM '+t) for t in ['customers','manufacturers','suppliers','warehouses','products','orders','order_lines','invoice_lines','purchase_lines','inventory_movements','inventory_balances','quote_lines','service_events','pricing_records','direct_fulfillment']}
booked=scalar('SELECT sum(ordered_qty*unit_price_cents) FROM order_lines');recognized=scalar('SELECT sum(revenue_cents) FROM invoice_lines');cost=scalar('SELECT sum(cost_cents) FROM invoice_lines')
openvalue=scalar('SELECT sum((ordered_qty-shipped_qty)*unit_price_cents) FROM order_lines');inv=scalar('SELECT sum(b.on_hand_qty*p.unit_cost_cents) FROM inventory_balances b JOIN products p ON b.product_id=p.id')
overdue=scalar("SELECT count(*) FROM order_lines WHERE shipped_qty<ordered_qty AND requested_date<'2026-10-01'")
due=scalar("SELECT count(*) FROM order_lines WHERE requested_date<'2026-10-01'");ontime=scalar("SELECT count(*) FROM order_lines WHERE requested_date<'2026-10-01' AND delivered_qty=ordered_qty AND delivered_date<=requested_date")
monthly=[dict(zip(['month','bookedRevenueCents','recognizedRevenueCents','grossProfitCents'],row)) for row in c.execute("SELECT substr(o.order_date,1,7),sum(l.ordered_qty*l.unit_price_cents),sum(l.shipped_qty*l.unit_price_cents),sum(l.shipped_qty*(l.unit_price_cents-l.unit_cost_cents)) FROM order_lines l JOIN orders o ON o.id=l.order_id GROUP BY 1")]
# Monthly recognized trend must use actual invoice month, not booking month.
for m in monthly:
    row=c.execute('SELECT coalesce(sum(revenue_cents),0),coalesce(sum(revenue_cents-cost_cents),0) FROM invoice_lines WHERE substr(invoice_date,1,7)=?',(m['month'],)).fetchone();m['recognizedRevenueCents'],m['grossProfitCents']=row
cases=[]
for sid,title,owner,desc,rec,depts in [
('SUPPLY-001','Supplier delay threatens customer commitments','Planning & Sourcing','Eight overdue lines have zero local stock and an overdue unreceived purchase order.','Validate supplier recovery dates, review alternatives, and request approval to assign customer communication.',['Planning & Sourcing','Sales','Customer Service','Operations']),
('MARGIN-002','Fulfilled orders show margin erosion','Commercial Excellence','Six fulfilled lines were priced at 3% above cost rather than the standard list price.','Review discount authorization and draft a pricing correction for future quotes.',['Commercial Excellence','Sales','Finance']),
('STOCK-003','Inventory imbalance blocks fulfillment','Operations','Six overdue lines have zero local stock while another warehouse holds 500 units of each item.','Check transfer feasibility and draft coordinated warehouse and customer-service assignments.',['Operations','Planning & Sourcing','Customer Service','Finance'])]:
    subset=[l for l in lines if l[11]==sid]; exposure=sum((l[4]-l[5])*l[6] for l in subset) if sid!='MARGIN-002' else sum(l[5]*(products[l[2]][1]-l[6]) for l in subset)
    cases.append(dict(id=sid,title=title,owner=owner,department=owner,severity='High',status='Awaiting review',exposureCents=exposure,impact=exposure/100,impactLabel='Open order value' if sid!='MARGIN-002' else 'Discount versus list',affectedOrderIds=sorted(set(l[1] for l in subset)),description=desc,evidence=[{'label':'Affected order lines','value':len(subset)},{'label':'Source','value':'Synthetic SQLite order_lines; scenario_id = '+sid}],recommendation=rec,departments=depts))
for sid,title,owner,desc,rec in [('DIRECT-004','Manufacturer confirmation overdue','Planning & Sourcing','Manufacturer has not confirmed the direct shipment.','Contact manufacturer and draft an updated customer commitment.'),('DIRECT-005','Direct shipment partially fulfilled','Customer Service','Manufacturer shipped only part of the customer quantity.','Confirm remaining shipment and coordinate customer communication.'),('DIRECT-006','Direct delivery invoice discrepancy','Finance','Supplier invoice quantity exceeds the confirmed proof-of-delivery quantity by two units.','Reconcile supplier invoice to proof of delivery before approval.')]:
    l=next(x for x in lines if x[11]==sid);impact=(l[4]-l[5])*l[6] if sid!='DIRECT-006' else 2*l[7]
    cases.append(dict(id=sid,title=title,owner=owner,department=owner,severity='High',status='Awaiting review',exposureCents=impact,impact=impact/100,impactLabel='Open order value' if sid!='DIRECT-006' else 'Supplier invoice discrepancy',affectedOrderIds=[l[1]],description=desc,evidence=[{'label':'Order line','value':l[0]},{'label':'Fulfillment','value':'Manufacturer direct to customer; no warehouse movement'}],recommendation=rec,departments=[owner,'Sales','Customer Service']))
roles=[]
for rid,name,table,focus in [('executive','Executive / VP','order_lines','Cross-department business exposure'),('sales','Sales','order_lines','Customer commitments and bookings'),('commercial','Commercial Excellence','pricing_records','Pricing and margin'),('service','Customer Service','service_events','Customer issues and follow-up'),('operations','Operations','inventory_movements','Warehouse fulfillment and stock'),('planning','Planning & Sourcing','purchase_lines','Supplier reliability and replenishment'),('finance','Finance','invoice_lines','Recognized revenue and cost'),('analytics','Business Operations & Analytics','order_lines','Performance and recurring exceptions')]:roles.append(dict(id=rid,name=name,recordCount=counts[table],sourceTable=table,focus=focus))
assumptions=['Entirely fictional Northstar Scientific; not a replica of verified Avantor configuration.','27 fictional warehouses (20 USA, 7 EU), 3,000 suppliers, 100,000 customers and products; organization master counts reflect plausible cardinality, not 100,000 fake warehouses or suppliers.','USD only; no tax, FX, returns, freight, payment ledger or production SAP integration.','12 historical months plus simulation as-of 2026-10-01; shipped line invoiced in full on shipment date.','100,000+ relevant shared records per audience; facts are not duplicated per department.','Delivery occurs two days after shipment; future arrivals remain undelivered. OTIF uses actual delivery and requested customer date (CRD), includes overdue open lines in denominator; original committed date retained separately.','Booked revenue = ordered quantity × net price; recognized revenue = invoiced shipment value under demo simplification.','Inventory openings cover chronological movements plus a 20–40 unit buffer; shortages use explicit simulation-day count adjustments; replenishment is simplified.','Monthly revenue trend uses invoice dates; current simulation-day invoices are outside historical 12-month trend.','Manufacturers (500) are distinct from procurement suppliers (3,000); direct_fulfillment stores synthetic PO references, confirmation, shipment, delivery and supplier invoice quantity. Supplier invoice mismatch is an exception, not recognized customer revenue.',
'Recommendations are scripted proposals; no autonomous assignments, actual AI inference, or operational writeback.']
summary=dict(revenue=recognized/100,marginPct=round((recognized-cost)/recognized*100,2),openOrders=scalar('SELECT count(DISTINCT order_id) FROM order_lines WHERE shipped_qty<ordered_qty'),atRiskRevenue=sum(x['exposureCents'] for x in cases if x['id'] not in ['MARGIN-002','DIRECT-006'])/100,inventoryValue=inv/100)
data=dict(company='Northstar Scientific',asOf=str(today),currency='USD',synthetic=True,meta={'company':'Northstar Scientific','asOf':str(today),'synthetic':True,'currency':'USD'},summary=summary,metrics=dict(bookedRevenueCents=booked,recognizedRevenueCents=recognized,openOrderValueCents=openvalue,grossProfitCents=recognized-cost,inventoryValueCents=inv,otifPercent=round(100*ontime/due,2),overdueOpenLines=overdue),monthly=monthly,trend=[{'label':m['month'],'revenue':m['recognizedRevenueCents']/100} for m in monthly],roles=roles,departments=roles,cases=cases,network=[dict(zip(['id','name','region','country'],row)) for row in c.execute('SELECT * FROM warehouses')],counts=counts,assumptions=assumptions)
data['departmentMetrics']={
'openServiceEvents':scalar("SELECT count(*) FROM service_events WHERE status='Open'"),
'openPurchaseLines':scalar('SELECT count(*) FROM purchase_lines WHERE received_qty<ordered_qty'),
'directOpenLines':scalar("SELECT count(*) FROM order_lines WHERE fulfillment_mode='DIRECT' AND delivered_qty<ordered_qty"),
'directUnshippedValueCents':scalar("SELECT sum((ordered_qty-shipped_qty)*unit_price_cents) FROM order_lines WHERE fulfillment_mode='DIRECT'"),
'pricingExceptions':scalar('SELECT count(*) FROM order_lines l JOIN pricing_records p ON l.product_id=p.product_id WHERE l.unit_price_cents<p.floor_price_cents'),
'pendingDirectConfirmations':scalar("SELECT count(*) FROM direct_fulfillment WHERE confirmation_status='Pending'"),
'supplierInvoiceDiscrepancies':scalar('SELECT count(*) FROM direct_fulfillment WHERE supplier_invoice_qty!=shipped_qty'),
'openQuotes':scalar("SELECT count(*) FROM quote_lines WHERE status='Open'")}
for case in cases:
    case['departments']=list(dict.fromkeys(case['departments']))
    if case['id'].startswith('DIRECT'):
        l=next(x for x in lines if x[11]==case['id']);customer=orders[l[1]-1][1]
        case['evidence'].extend([{'label':'Customer','value':f'Fictional Research Customer {customer:06}'},{'label':'Manufacturer','value':f'Fictional Manufacturer {l[14]:04}'},{'label':'Supplier','value':f'Fictional Supplier {l[13]:04}'},{'label':'Direct PO reference','value':f'DPO-{l[0]}'}])
        delivery_date,delivered_qty=c.execute('SELECT delivered_date,delivered_qty FROM order_lines WHERE id=?',(l[0],)).fetchone()
        confirmation,pod,supplier_invoice_qty=c.execute('SELECT confirmation_status,proof_of_delivery,supplier_invoice_qty FROM direct_fulfillment WHERE order_line_id=?',(l[0],)).fetchone()
        case['evidence'].extend([
            {'label':'Ordered quantity','value':l[4]},
            {'label':'Shipped quantity','value':l[5]},
            {'label':'Delivered quantity (POD)','value':delivered_qty},
            {'label':'Remaining to ship','value':l[4]-l[5]},
            {'label':'Remaining to deliver','value':l[4]-delivered_qty},
            {'label':'Customer requested delivery date','value':l[8]},
            {'label':'Original customer committed date','value':l[9]},
            {'label':'Manufacturer confirmation','value':confirmation},
            {'label':'Confirmed delivery date','value':l[9] if confirmation=='Confirmed' else 'Not confirmed'},
            {'label':'Actual shipment date','value':l[10] or 'Not shipped'},
            {'label':'Actual delivery date','value':delivery_date or 'Not delivered'},
            {'label':'Proof of delivery','value':pod or 'Not available'},
            {'label':'Supplier invoiced quantity','value':supplier_invoice_qty},
            {'label':'Supplier invoice versus POD quantity','value':supplier_invoice_qty-delivered_qty}])
checks={'foreign_keys':len(c.execute('PRAGMA foreign_key_check').fetchall())==0,'integrity':scalar('PRAGMA integrity_check')=='ok','quantity_bounds':scalar('SELECT count(*) FROM order_lines WHERE shipped_qty<0 OR shipped_qty>ordered_qty')==0,'invoice_reconciliation':scalar('SELECT count(*) FROM invoice_lines i JOIN order_lines l ON l.id=i.order_line_id WHERE i.quantity!=l.shipped_qty OR i.revenue_cents!=l.shipped_qty*l.unit_price_cents OR i.cost_cents!=l.shipped_qty*l.unit_cost_cents')==0,'booked_equals_recognized_plus_open':booked==recognized+openvalue,'inventory_reconciliation':scalar('SELECT count(*) FROM inventory_balances b LEFT JOIN (SELECT product_id,warehouse_id,sum(quantity) delta FROM inventory_movements GROUP BY 1,2) m ON b.product_id=m.product_id AND b.warehouse_id=m.warehouse_id WHERE b.on_hand_qty!=b.opening_qty+coalesce(m.delta,0)')==0,'historical_nonnegative_stock':scalar('SELECT min(b.opening_qty+m.running) FROM (SELECT product_id,warehouse_id,sum(quantity) OVER (PARTITION BY product_id,warehouse_id ORDER BY movement_date,id) running FROM inventory_movements) m JOIN inventory_balances b ON b.product_id=m.product_id AND b.warehouse_id=m.warehouse_id')>=0,'nonnegative_stock':scalar('SELECT min(on_hand_qty) FROM inventory_balances')>=0,'all_audiences_100k':all(x['recordCount']>=100000 for x in roles),'direct_no_warehouse_movements':scalar("SELECT count(*) FROM inventory_movements m JOIN order_lines l ON l.id=m.order_line_id WHERE l.fulfillment_mode='DIRECT'")==0,'service_after_order':scalar('SELECT count(*) FROM service_events e JOIN order_lines l ON l.id=e.order_line_id JOIN orders o ON o.id=l.order_id WHERE e.event_date<o.order_date')==0,'delivery_quantity_bounds':scalar('SELECT count(*) FROM order_lines WHERE delivered_qty>shipped_qty')==0,'direct_quantity_bounds':scalar('SELECT count(*) FROM direct_fulfillment WHERE delivered_qty>shipped_qty OR shipped_qty>ordered_qty')==0,'no_future_shipments':scalar("SELECT count(*) FROM order_lines WHERE shipped_date>'2026-10-01'")==0}
assert all(checks.values()),checks
(OUT/'dashboard.json').write_text(json.dumps(data,indent=2));(OUT/'dashboard-data.js').write_text('window.DEMO_DATA = '+json.dumps(data)+';\n')
(OUT/'validation.json').write_text(json.dumps({'passed':all(checks.values()),'checks':checks,'counts':counts,'seed':417},indent=2))
perspectives=[]
role_topics={
'executive':[('Cross-functional customer exposure','SUPPLY-001'),('Profitability exception','MARGIN-002'),('Working-capital recovery','STOCK-003'),('Regional performance divergence',None)],
'sales':[('Customer commitment recovery','SUPPLY-001'),('Discount exception','MARGIN-002'),('Partial direct order communication','DIRECT-005'),('Key-account revenue decline',None)],
'commercial':[('Below-target price review','MARGIN-002'),('Price floor compliance','MARGIN-002'),('Discount value analysis','MARGIN-002'),('Freight margin leakage',None)],
'service':[('Late order escalation','SUPPLY-001'),('Partial delivery follow-up','DIRECT-005'),('Manufacturer confirmation chase','DIRECT-004'),('Complaint recurrence',None)],
'operations':[('Transfer opportunity','STOCK-003'),('Stock discrepancy review','STOCK-003'),('Overdue fulfillment recovery','SUPPLY-001'),('Warehouse capacity constraint',None)],
'planning':[('Supplier overdue receipt','SUPPLY-001'),('Direct supplier confirmation','DIRECT-004'),('Interwarehouse replenishment','STOCK-003'),('Demand forecast error',None)],
'finance':[('Discount impact on gross profit','MARGIN-002'),('Supplier invoice versus delivery','DIRECT-006'),('Open order revenue exposure','SUPPLY-001'),('Overdue receivables',None)],
'analytics':[('OTIF root-cause review','SUPPLY-001'),('Inventory imbalance pattern','STOCK-003'),('Direct fulfillment exception','DIRECT-005'),('Repeated process bottleneck',None)]}
for role in roles:
    for topic,seed in role_topics[role['id']]:perspectives.append({'audience':role['name'],'scenario':topic,'seededCaseId':seed,'status':'Seeded perspective' if seed else 'Designed only; additional data required','humanApproval':'Required before assignment'})
(OUT/'scenario-perspectives.json').write_text(json.dumps(perspectives,indent=2))
(OUT/'README.txt').write_text('NORTHSTAR SCIENTIFIC — SYNTHETIC DEMONSTRATION DATA\n\nRebuild: python3 outputs/operations-demo/tools/generate_data.py\nRebuild replaces only generated northstar.sqlite and JSON/JS outputs.\nNo real customer, employee, supplier or transaction data.\n\n'+ '\n'.join(assumptions)+'\n\nTABLE DICTIONARY\ncustomers/manufacturers/suppliers/warehouses/products: fictional masters; warehouses include country.\norders: header, customer, booking date and sales region.\norder_lines: quantities, integer cent net price and cost, customer requested date, original committed date, shipment/delivery dates and quantities, fulfillment mode and scenario.\ninvoice_lines: recognized shipment revenue and matching cost; primary id matches line.\npurchase_lines: ordered/received quantities and supplier dates.\ninventory_movements: signed receipts, shipment issues and count adjustments; zero receipt rows denote delayed receipt placeholders.\ninventory_balances: opening and current stock per product/location.\nquote_lines: fictional quotations, not additional bookings.\nservice_events: service workflow events referencing orders.\npricing_records: effective product list and floor prices.\ndirect_fulfillment: supplier/manufacturer references, direct PO reference, confirmation status, quantities, proof of delivery and supplier invoice quantity; customer invoice remains invoice_lines.\n\nREADING THE DEMO\nDashboard financial values are computed from SQLite. summary/trend/impact values use USD dollars; *Cents fields use integer cents.\nCase exposures are different measures and must not be summed indiscriminately: margin case is discount versus list; DIRECT-006 is supplier invoice discrepancy; other cases are open order value.\n12-month charts exclude simulation-day invoices; top-level recognized revenue includes them.\nCase recommendations are scripted, not machine-generated. 32 scenario perspectives are a design matrix over 6 seeded cross-functional cases, not 32 implemented business simulations.\nThere are 100k masters each for customers/products; suppliers/warehouses deliberately have realistic smaller counts as confirmed fictional scale.\n')
c.close();print(json.dumps({'counts':counts,'sizeBytes':DB.stat().st_size,'checks':checks,'summary':summary},indent=2))
