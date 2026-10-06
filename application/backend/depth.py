"""Bounded, read-only department and entity perspectives over synthetic facts."""
from fastapi import HTTPException
from . import cohorts
from .db import open_business


def register_depth(app, data_dir, seed, order_query, records_query):
    business = lambda: open_business(data_dir)

    def metric(key, label, value, unit, definition):
        return dict(key=key, label=label, value=value or 0, unit=unit, definition=definition)

    def amount(db, query, args=()):
        return db.execute(query, args).fetchone()[0] or 0

    @app.get('/api/departments/{role}')
    def department(role: str):
        snapshot = seed()
        audience = next((x for x in snapshot['roles'] if x['id'] == role), None)
        if not audience:
            raise HTTPException(404, 'Unknown department')
        as_of = snapshot['asOf']
        metrics = []
        with business() as db:
            def add(key, label, sql, unit='count', definition='', args=()):
                metrics.append(metric(key, label, amount(db, sql, args), unit, definition))
            if role == 'executive':
                add('invoiced_sales', 'Invoiced sales', 'SELECT sum(revenue_cents) FROM invoice_lines', 'cents', 'All invoiced shipment value in the dataset, including simulation day; not a revenue-recognition policy.')
                add('open_value', 'Open order value', 'SELECT sum((ordered_qty-shipped_qty)*unit_price_cents) FROM order_lines', 'cents', 'Unshipped quantity times order net price; not forecast lost revenue.')
                add('affected_customers', 'Customers in seeded cases', 'SELECT count(DISTINCT o.customer_id) FROM orders o JOIN order_lines l ON l.order_id=o.id WHERE l.scenario_id IS NOT NULL', definition='Distinct customers with a scenario-tagged order line.')
            elif role == 'sales':
                add('bookings', 'Order bookings', 'SELECT sum(ordered_qty*unit_price_cents) FROM order_lines', 'cents', 'Ordered quantity times net price across the dataset.')
                add('open_quotes', 'Open quote lines', "SELECT count(*) FROM quote_lines WHERE status='Open'", definition='Quote lines marked Open; quotes are not booked orders.')
                add('customers_open', 'Customers awaiting complete delivery', 'SELECT count(DISTINCT o.customer_id) FROM orders o JOIN order_lines l ON l.order_id=o.id WHERE l.delivered_qty<l.ordered_qty', definition='Distinct customers with at least one incompletely delivered line, including in-transit shipments.')
            elif role == 'commercial':
                add('below_floor', 'Lines below pricing floor', 'SELECT count(*) FROM order_lines l JOIN pricing_records pr ON pr.product_id=l.product_id WHERE l.unit_price_cents<pr.floor_price_cents', definition='Line net price below the single effective demo pricing floor.')
                add('discount', 'Discount versus list', 'SELECT sum(l.ordered_qty*max(0,p.list_price_cents-l.unit_price_cents)) FROM order_lines l JOIN products p ON p.id=l.product_id', 'cents', 'Positive ordered-price difference versus list; not lost profit or realized revenue.')
                add('gross_margin', 'Invoiced gross margin', 'SELECT 100.0*sum(revenue_cents-cost_cents)/nullif(sum(revenue_cents),0) FROM invoice_lines', 'percent', 'Invoiced sales less modeled product cost, divided by invoiced sales; excludes freight and overhead.')
            elif role == 'service':
                add('open_events', 'Open service events', "SELECT count(*) FROM service_events WHERE status='Open'", definition='Events, not unique cases or customers, with Open status.')
                add('customers_open_events', 'Customers with open events', "SELECT count(DISTINCT o.customer_id) FROM service_events e JOIN order_lines l ON l.id=e.order_line_id JOIN orders o ON o.id=l.order_id WHERE e.status='Open'", definition='Distinct customers linked to an Open service event.')
                add('overdue_delivery', 'Past-due incomplete delivery lines', 'SELECT count(*) FROM order_lines WHERE delivered_qty<ordered_qty AND requested_date<?', args=(as_of,), definition='Requested date before simulation day and delivered quantity below ordered quantity.')
            elif role == 'operations':
                add('warehouse_backlog', 'Stock lines awaiting shipment', "SELECT count(*) FROM order_lines WHERE fulfillment_mode='STOCK' AND shipped_qty<ordered_qty", definition='Warehouse-fulfilled lines with unshipped quantity; excludes direct shipments.')
                add('inventory', 'On-hand inventory value', 'SELECT sum(b.on_hand_qty*p.unit_cost_cents) FROM inventory_balances b JOIN products p ON p.id=b.product_id', 'cents', 'Current warehouse on-hand units at modeled product cost; includes synthetic adjustments.')
                add('zero_positions', 'Zero-stock positions', 'SELECT count(*) FROM inventory_balances WHERE on_hand_qty=0', definition='Product/warehouse positions at zero, not a demand-weighted stockout rate.')
            elif role == 'planning':
                add('overdue_po', 'Overdue unreceived PO lines', 'SELECT count(*) FROM purchase_lines WHERE received_qty<ordered_qty AND expected_date<?', args=(as_of,), definition='Expected receipt before simulation day with remaining quantity.')
                add('pending_direct', 'Pending direct confirmations', "SELECT count(*) FROM direct_fulfillment WHERE confirmation_status='Pending'", definition='Direct-fulfillment lines awaiting supplier/manufacturer confirmation.')
                add('shortage_units', 'Unreceived purchase units', 'SELECT sum(ordered_qty-received_qty) FROM purchase_lines', definition='Ordered less received purchase units, including quantities not yet overdue.')
            elif role == 'finance':
                add('invoiced_sales', 'Invoiced sales', 'SELECT sum(revenue_cents) FROM invoice_lines', 'cents', 'Invoiced shipment value; payment, returns, tax and recognition policy are not modeled.')
                add('gross_profit', 'Modeled gross profit', 'SELECT sum(revenue_cents-cost_cents) FROM invoice_lines', 'cents', 'Invoiced sales less modeled product cost; excludes freight and overhead.')
                add('invoice_discrepancy', 'Direct invoice excess at cost', 'SELECT sum(max(0,d.supplier_invoice_qty-d.delivered_qty)*l.unit_cost_cents) FROM direct_fulfillment d JOIN order_lines l ON l.id=d.order_line_id', 'cents', 'Positive supplier invoice quantity above delivered quantity, valued at modeled unit cost.')
            else:
                add('scenario_lines', 'Seeded exception lines', 'SELECT count(*) FROM order_lines WHERE scenario_id IS NOT NULL', definition='Tagged lines in the six seeded scenarios; not all operational exceptions.')
                add('late_deliveries', 'Late completed delivery lines', 'SELECT count(*) FROM order_lines WHERE delivered_qty=ordered_qty AND delivered_date>requested_date', definition='Fully delivered lines whose actual delivery was after the requested date.')
                add('otif', 'Delivery OTIF', 'SELECT 100.0*sum(CASE WHEN delivered_qty=ordered_qty AND delivered_date<=requested_date THEN 1 ELSE 0 END)/nullif(count(*),0) FROM order_lines WHERE requested_date<?', 'percent', 'Line-level complete delivery by requested date; includes overdue open lines, excludes lines due on/after simulation day.', (as_of,))
        predicate, label = cohorts.COHORTS[role]
        queue = order_query(page_size=10, sort='order_date', direction='desc', internal_where=predicate)
        selected_cases = snapshot['cases'] if role in ('executive', 'analytics') else [x for x in snapshot['cases'] if audience['name'] in x['departments']]
        return dict(role=role, title=audience['name'], asOf=as_of, metrics=metrics, queue={**queue, 'label': label + ' (up to 10)', 'scope': {'department': role}}, cases=selected_cases, synthetic=True)

    @app.get('/api/entities/{kind}/{entity_id}')
    def entity(kind: str, entity_id: int):
        mapping = {'customers': ('o.customer_id', 'customer_id'), 'products': ('l.product_id', 'product_id'), 'manufacturers': ('p.manufacturer_id', 'manufacturer_id')}
        if kind not in mapping or entity_id < 1:
            raise HTTPException(404, 'Unknown entity kind or identifier')
        column, filter_key = mapping[kind]
        joins = ' FROM order_lines l JOIN orders o ON o.id=l.order_id JOIN products p ON p.id=l.product_id'
        clause = ' WHERE ' + column + '=?'
        with business() as db:
            row = db.execute(f'SELECT * FROM {kind} WHERE id=?', (entity_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Entity not found')
            attributes = dict(row)
            aggregate = db.execute('SELECT count(*) lines,count(DISTINCT o.id) orders,coalesce(sum(l.ordered_qty*l.unit_price_cents),0) bookings,coalesce(sum((l.ordered_qty-l.shipped_qty)*l.unit_price_cents),0) open_value' + joins + clause, (entity_id,)).fetchone()
            metrics = [metric('order_lines', 'Order lines', aggregate['lines'], 'count', 'All order lines linked to this entity.'), metric('orders', 'Orders', aggregate['orders'], 'count', 'Distinct orders containing linked lines.'), metric('bookings', 'Order bookings', aggregate['bookings'], 'cents', 'Linked ordered units at line net price.'), metric('open_value', 'Open order value', aggregate['open_value'], 'cents', 'Linked unshipped units at line net price.')]
            invoiced = amount(db, 'SELECT sum(i.revenue_cents)' + joins + ' JOIN invoice_lines i ON i.order_line_id=l.id' + clause, (entity_id,))
            metrics.append(metric('invoiced_sales', 'Invoiced sales', invoiced, 'cents', 'Actual invoice values for scoped lines; not a revenue-recognition policy.'))
            related = {}
            for target, expr in [('customers','o.customer_id'), ('products','p.id'), ('manufacturers','p.manufacturer_id')]:
                if target == kind:
                    continue
                related[target] = [dict(x) for x in db.execute('SELECT DISTINCT e.id,e.name' + joins + f' JOIN {target} e ON e.id={expr}' + clause + ' ORDER BY e.id LIMIT 10', (entity_id,)).fetchall()]
            scenario_ids = {x[0] for x in db.execute('SELECT DISTINCT l.scenario_id' + joins + clause + ' AND l.scenario_id IS NOT NULL', (entity_id,))}
            inventory = [dict(x) for x in db.execute('SELECT b.warehouse_id,w.name warehouse_name,w.region,b.on_hand_qty FROM inventory_balances b JOIN warehouses w ON w.id=b.warehouse_id WHERE b.product_id=? ORDER BY b.warehouse_id', (entity_id,))] if kind == 'products' else []
        source_context = {'service': records_query('service',page_size=10,customer_id=entity_id)} if kind == 'customers' else {'purchases':records_query('purchases',page_size=10,product_id=entity_id)} if kind == 'products' else {}
        return dict(kind=kind, id=entity_id, name=attributes['name'], attributes=attributes, metrics=metrics, related=related, inventory=inventory, sourceContext=source_context, inventoryDefinition='On-hand units only; reservations, availability and transfer feasibility are not modeled.', relatedNote='Up to 10 linked entities per kind, derived from scoped order lines.', orders=order_query(page_size=10, sort='order_date', direction='desc', **{filter_key: entity_id}), cases=[x for x in seed()['cases'] if x['id'] in scenario_ids], synthetic=True)
