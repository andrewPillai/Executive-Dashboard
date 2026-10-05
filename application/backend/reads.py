"""Read-only source records, reporting, and bounded order enrichment."""
import calendar
import sqlite3
from datetime import date
from contextlib import contextmanager
from fastapi import HTTPException, Query


def enrich_orders(db, items, as_of):
    if not items:
        return items
    ids = [x['id'] for x in items]
    products = list({x['product_id'] for x in items})
    marks = ','.join('?' for _ in ids)
    pmarks = ','.join('?' for _ in products)
    pricing = {x['product_id']: dict(x) for x in db.execute(f'SELECT product_id,list_price_cents,floor_price_cents FROM pricing_records WHERE product_id IN ({pmarks})', products)}
    services = {}
    for row in db.execute(f'SELECT * FROM service_events WHERE order_line_id IN ({marks}) ORDER BY event_date,id', ids):
        services[row['order_line_id']] = dict(row)
    purchases = {}
    for row in db.execute(f'SELECT * FROM purchase_lines WHERE product_id IN ({pmarks}) AND received_qty<ordered_qty ORDER BY expected_date,id', products):
        purchases.setdefault((row['product_id'], row['warehouse_id']), dict(row))
    for row in items:
        price = pricing.get(row['product_id'], {})
        row.update(price)
        row['unit_margin_cents'] = row['unit_price_cents'] - row['unit_cost_cents']
        row['discount_vs_list_cents'] = max(0, price.get('list_price_cents', row['unit_price_cents']) - row['unit_price_cents']) * row['ordered_qty']
        row['days_past_requested'] = max(0, (date.fromisoformat(as_of) - date.fromisoformat(row['requested_date'])).days)
        row['delivery_lateness_days'] = max(0, (date.fromisoformat(row['delivered_date']) - date.fromisoformat(row['requested_date'])).days) if row['delivered_date'] else None
        event = services.get(row['id'])
        row.update(service_category=event['category'] if event else None, service_status=event['status'] if event else None, service_event_date=event['event_date'] if event else None, service_age_days=(date.fromisoformat(as_of)-date.fromisoformat(event['event_date'])).days if event else None)
        po = purchases.get((row['product_id'], row['warehouse_id']))
        row.update(candidate_po_id=po['id'] if po else None, candidate_po_expected_date=po['expected_date'] if po else None, candidate_po_open_qty=po['ordered_qty']-po['received_qty'] if po else None)
    return items


def register_reads(app, data_dir, seed):
    @contextmanager
    def business():
        db = sqlite3.connect((data_dir / 'northstar.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def records_query(kind, page=1, page_size=25, customer_id=None, product_id=None, order_line_id=None, status=None, sort='newest', open_only=False):
        if kind not in ('quotes','service','purchases'):
            raise HTTPException(404, 'Unknown record kind')
        if sort not in ('oldest', 'newest'):
            raise HTTPException(422, 'Unsupported record sort')
        if open_only and kind != 'purchases':
            raise HTTPException(422, 'open_only is only supported for purchases')
        where, args = [], []
        if kind == 'quotes':
            source = ' FROM quote_lines r JOIN customers cu ON cu.id=r.customer_id JOIN products p ON p.id=r.product_id'
            fields = 'r.*,cu.name customer_name,p.name product_name'
            columns = {'customer_id':'r.customer_id','product_id':'r.product_id','status':'r.status'}
            order = 'r.quote_date DESC,r.id ASC'
            definition = 'Quote lines, not booked orders. Status is the synthetic source status.'
        elif kind == 'service':
            source = ' FROM service_events r JOIN order_lines l ON l.id=r.order_line_id JOIN orders o ON o.id=l.order_id JOIN customers cu ON cu.id=o.customer_id JOIN products p ON p.id=l.product_id'
            fields = 'r.*,o.customer_id,cu.name customer_name,l.product_id,p.name product_name,l.order_id,l.requested_date,l.delivered_date,l.ordered_qty,l.delivered_qty'
            columns = {'customer_id':'o.customer_id','product_id':'l.product_id','order_line_id':'r.order_line_id','status':'r.status'}
            order = 'r.event_date DESC,r.id ASC'
            definition = 'Service events linked to order lines. Age is elapsed days since event, not SLA breach or resolution duration.'
        else:
            source = ' FROM purchase_lines r JOIN products p ON p.id=r.product_id JOIN suppliers s ON s.id=r.supplier_id JOIN warehouses w ON w.id=r.warehouse_id'
            fields = 'r.*,p.name product_name,s.name supplier_name,w.name warehouse_name,(r.ordered_qty-r.received_qty) open_qty'
            columns = {'product_id':'r.product_id'}
            order = 'r.expected_date DESC,r.id ASC'
            definition = 'Purchase lines at a product and warehouse. Matching demand is a supply candidate, not reserved or allocated stock.'
        for key, value in [('customer_id', customer_id), ('product_id', product_id), ('order_line_id', order_line_id), ('status', status)]:
            if value is not None:
                if key not in columns:
                    raise HTTPException(422, f'{key} is not a supported filter for {kind}')
                where.append(columns[key] + '=?')
                args.append(value)
        if open_only:
            where.append('r.received_qty<r.ordered_qty')
        if sort == 'oldest':
            order = order.replace(' DESC', ' ASC')
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with business() as db:
            total = db.execute('SELECT count(*)' + source + clause, args).fetchone()[0]
            items = [dict(x) for x in db.execute('SELECT ' + fields + source + clause + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?', args+[page_size,(page-1)*page_size])]
        as_of = date.fromisoformat(seed()['asOf'])
        for item in items:
            if kind == 'service':
                item['age_days'] = (as_of-date.fromisoformat(item['event_date'])).days
            if kind == 'purchases':
                item['overdue_days'] = max(0,(as_of-date.fromisoformat(item['expected_date'])).days) if item['open_qty'] else 0
        return dict(kind=kind, items=items,total=total,page=page,page_size=page_size,sort=sort,open_only=open_only,definition=definition)

    @app.get('/api/records/{kind}')
    def records(kind: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), customer_id: int | None = Query(None, ge=1), product_id: int | None = Query(None, ge=1), order_line_id: int | None = Query(None, ge=1), status: str | None = Query(None, max_length=40), sort: str = 'newest', open_only: bool = False):
        return records_query(kind,page,page_size,customer_id,product_id,order_line_id,status,sort,open_only)

    @app.get('/api/reports')
    def reports(period: str = 'all', region: str = 'all'):
        if period not in ('all','2026-09','2026-10') or region not in ('all','USA','EU'):
            raise HTTPException(422, 'Unsupported reporting period or region')
        as_of = seed()['asOf']
        source = ' FROM invoice_lines i JOIN order_lines l ON l.id=i.order_line_id JOIN orders o ON o.id=l.order_id'
        def filters(selected):
            terms, args = ['i.invoice_date<=?'], [as_of]
            if selected != 'all':
                terms.append('substr(i.invoice_date,1,7)=?');args.append(selected)
            if region != 'all':
                terms.append('o.region=?');args.append(region)
            return ' WHERE '+' AND '.join(terms),args
        with business() as db:
            clause,args=filters(period)
            rows=[dict(x) for x in db.execute('SELECT substr(i.invoice_date,1,7) month,sum(i.revenue_cents) invoiced_sales_cents,sum(i.revenue_cents-i.cost_cents) gross_profit_cents'+source+clause+' GROUP BY 1 ORDER BY 1',args)]
            sales=sum(x['invoiced_sales_cents'] for x in rows);profit=sum(x['gross_profit_cents'] for x in rows)
            previous=None
            operational_terms,operational_args=['l.requested_date<?'],[as_of]
            if period!='all':
                operational_terms.append('substr(l.requested_date,1,7)=?');operational_args.append(period)
            if region!='all':
                operational_terms.append('o.region=?');operational_args.append(region)
            operational=[dict(x) for x in db.execute('''SELECT substr(l.requested_date,1,7) month,count(*) eligible_lines,
                sum(CASE WHEN l.delivered_qty=l.ordered_qty AND l.delivered_date<=l.requested_date THEN 1 ELSE 0 END) otif_lines,
                sum(CASE WHEN l.delivered_qty=l.ordered_qty AND l.delivered_date>l.requested_date THEN 1 ELSE 0 END) late_complete_lines
                FROM order_lines l JOIN orders o ON o.id=l.order_id WHERE '''+' AND '.join(operational_terms)+' GROUP BY 1 ORDER BY 1',operational_args)]
            for item in operational:
                item['otif_percent']=round(100*item['otif_lines']/item['eligible_lines'],2)
            if period!='all':
                year,month=map(int,period.split('-'));previous_month=date(year-1,12,1) if month==1 else date(year,month-1,1)
                previous_period=previous_month.strftime('%Y-%m')
                previous_clause,previous_args=filters(previous_period)
                # Incomplete current month compares the same number of elapsed calendar days.
                partial=period==as_of[:7]
                if partial:
                    day=min(int(as_of[-2:]),calendar.monthrange(previous_month.year,previous_month.month)[1])
                    previous_clause+=' AND i.invoice_date<=?';previous_args.append(previous_month.replace(day=day).isoformat())
                prior=db.execute('SELECT coalesce(sum(i.revenue_cents),0),coalesce(sum(i.revenue_cents-i.cost_cents),0)'+source+previous_clause,previous_args).fetchone()
                previous=dict(period=previous_period,invoiced_sales_cents=prior[0],gross_profit_cents=prior[1],comparison='Same elapsed calendar days of prior month' if partial else 'Full prior calendar month')
        def metric(key,label,value,unit,definition):
            return dict(key=key,label=label,value=value,unit=unit,definition=definition)
        return dict(period=period,region=region,asOf=as_of,metrics=[metric('invoiced_sales','Invoiced sales',sales,'cents','Invoice-date selected sales; region is customer sales region, not fulfillment site.'),metric('gross_profit','Modeled gross profit',profit,'cents','Selected invoice sales less modeled product cost; excludes freight, returns and overhead.'),metric('margin','Modeled gross margin',round(profit/sales*100,2) if sales else None,'percent','Modeled gross profit divided by selected invoiced sales; unavailable if no sales.')],monthly=rows,operationalMonthly=operational,operationalDefinition='Requested-date months; eligible lines have requested date strictly before simulation day. OTIF means full delivery by requested date and includes overdue incomplete lines in denominator. Empty months have no eligible cohort, not zero performance. Region is customer sales region. This basis differs from invoice-date financial series.',previous=previous,definition='Invoice-date report through simulation day; monthly series reconciles exactly to selected totals. All includes simulation-day invoices.',synthetic=True)

    return records_query
