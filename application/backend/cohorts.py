"""Shared order cohort definitions; never interpolate user-supplied SQL."""
COHORTS = {
    'executive': ('l.scenario_id IS NOT NULL', 'Recent lines in seeded cross-department cases'),
    'sales': ('l.delivered_qty<l.ordered_qty', 'Recent customer commitments awaiting complete delivery, including in-transit quantities'),
    'commercial': ('l.id IN (SELECT fl.id FROM order_lines fl JOIN pricing_records pr ON pr.product_id=fl.product_id WHERE fl.unit_price_cents<pr.floor_price_cents)', 'Recent order lines priced below the demo floor'),
    'service': ("l.id IN (SELECT e.order_line_id FROM service_events e WHERE e.status='Open')", 'Recent order lines linked to an open service event'),
    'operations': ("l.fulfillment_mode='STOCK' AND l.shipped_qty<l.ordered_qty", 'Recent warehouse lines with unshipped quantity'),
    'planning': ("l.shipped_qty<l.ordered_qty AND ((l.product_id,l.warehouse_id) IN (SELECT pl.product_id,pl.warehouse_id FROM purchase_lines pl WHERE pl.received_qty<pl.ordered_qty) OR df.confirmation_status='Pending')", 'Recent unshipped lines with same-product/site unreceived PO candidates or pending direct confirmation; not allocated supply'),
    'finance': ('df.supplier_invoice_qty>df.delivered_qty OR l.id IN (SELECT fl.id FROM order_lines fl JOIN pricing_records pr ON pr.product_id=fl.product_id WHERE fl.unit_price_cents<pr.floor_price_cents)', 'Recent supplier quantity discrepancies and below-floor order lines'),
    'analytics': ('l.delivered_qty=l.ordered_qty AND l.delivered_date>l.requested_date', 'Recent fully delivered lines that missed requested delivery date'),
}
