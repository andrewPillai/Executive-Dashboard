NORTHSTAR SCIENTIFIC — SYNTHETIC DEMONSTRATION DATA

Rebuild: python3 outputs/operations-demo/tools/generate_data.py
Rebuild replaces only generated northstar.sqlite and JSON/JS outputs.
No real customer, employee, supplier or transaction data.

Entirely fictional Northstar Scientific; not a replica of verified Avantor configuration.
27 fictional warehouses (20 USA, 7 EU), 3,000 suppliers, 100,000 customers and products; organization master counts reflect plausible cardinality, not 100,000 fake warehouses or suppliers.
USD only; no tax, FX, returns, freight, payment ledger or production SAP integration.
12 historical months plus simulation as-of 2026-10-01; shipped line invoiced in full on shipment date.
100,000+ relevant shared records per audience; facts are not duplicated per department.
Delivery occurs two days after shipment; future arrivals remain undelivered. OTIF uses actual delivery and requested customer date (CRD), includes overdue open lines in denominator; original committed date retained separately.
Booked revenue = ordered quantity × net price; recognized revenue = invoiced shipment value under demo simplification.
Inventory openings cover chronological movements plus a 20–40 unit buffer; shortages use explicit simulation-day count adjustments; replenishment is simplified.
Monthly revenue trend uses invoice dates; current simulation-day invoices are outside historical 12-month trend.
Manufacturers (500) are distinct from procurement suppliers (3,000); direct_fulfillment stores synthetic PO references, confirmation, shipment, delivery and supplier invoice quantity. Supplier invoice mismatch is an exception, not recognized customer revenue.
Recommendations are scripted proposals; no autonomous assignments, actual AI inference, or operational writeback.

TABLE DICTIONARY
customers/manufacturers/suppliers/warehouses/products: fictional masters; warehouses include country.
orders: header, customer, booking date and sales region.
order_lines: quantities, integer cent net price and cost, customer requested date, original committed date, shipment/delivery dates and quantities, fulfillment mode and scenario.
invoice_lines: recognized shipment revenue and matching cost; primary id matches line.
purchase_lines: ordered/received quantities and supplier dates.
inventory_movements: signed receipts, shipment issues and count adjustments; zero receipt rows denote delayed receipt placeholders.
inventory_balances: opening and current stock per product/location.
quote_lines: fictional quotations, not additional bookings.
service_events: service workflow events referencing orders.
pricing_records: effective product list and floor prices.
direct_fulfillment: supplier/manufacturer references, direct PO reference, confirmation status, quantities, proof of delivery and supplier invoice quantity; customer invoice remains invoice_lines.

READING THE DEMO
Dashboard financial values are computed from SQLite. summary/trend/impact values use USD dollars; *Cents fields use integer cents.
Case exposures are different measures and must not be summed indiscriminately: margin case is discount versus list; DIRECT-006 is supplier invoice discrepancy; other cases are open order value.
12-month charts exclude simulation-day invoices; top-level recognized revenue includes them.
Case recommendations are scripted, not machine-generated. 32 scenario perspectives are a design matrix over 6 seeded cross-functional cases, not 32 implemented business simulations.
There are 100k masters each for customers/products; suppliers/warehouses deliberately have realistic smaller counts as confirmed fictional scale.
