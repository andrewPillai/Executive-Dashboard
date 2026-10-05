-- Schema exported from packaged application/data/northstar.sqlite

CREATE INDEX invoice_order_line ON invoice_lines(order_line_id);

CREATE INDEX lines_order ON order_lines(order_id);

CREATE INDEX movements_stock ON inventory_movements(product_id,warehouse_id);

CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,region TEXT,segment TEXT);

CREATE TABLE direct_fulfillment(order_line_id INTEGER PRIMARY KEY REFERENCES order_lines(id),supplier_id INTEGER REFERENCES suppliers(id),manufacturer_id INTEGER REFERENCES manufacturers(id),po_reference TEXT,confirmation_status TEXT,ordered_qty INTEGER,shipped_qty INTEGER,delivered_qty INTEGER,proof_of_delivery TEXT,supplier_invoice_qty INTEGER);

CREATE TABLE inventory_balances(product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),opening_qty INTEGER,on_hand_qty INTEGER,PRIMARY KEY(product_id,warehouse_id));

CREATE TABLE inventory_movements(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),movement_date TEXT,kind TEXT,quantity INTEGER,order_line_id INTEGER REFERENCES order_lines(id),purchase_line_id INTEGER REFERENCES purchase_lines(id));

CREATE TABLE invoice_lines(id INTEGER PRIMARY KEY,order_line_id INTEGER REFERENCES order_lines(id),invoice_date TEXT,quantity INTEGER,revenue_cents INTEGER,cost_cents INTEGER);

CREATE TABLE manufacturers(id INTEGER PRIMARY KEY,name TEXT);

CREATE TABLE order_lines(id INTEGER PRIMARY KEY,order_id INTEGER REFERENCES orders(id),product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),ordered_qty INTEGER,shipped_qty INTEGER,unit_price_cents INTEGER,unit_cost_cents INTEGER,requested_date TEXT,original_committed_date TEXT,shipped_date TEXT,scenario_id TEXT,fulfillment_mode TEXT,ship_from_supplier_id INTEGER REFERENCES suppliers(id),ship_from_manufacturer_id INTEGER REFERENCES manufacturers(id), delivered_date TEXT, delivered_qty INTEGER DEFAULT 0);

CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),order_date TEXT,region TEXT);

CREATE TABLE pricing_records(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),effective_date TEXT,list_price_cents INTEGER,floor_price_cents INTEGER);

CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE,name TEXT,category TEXT,supplier_id INTEGER REFERENCES suppliers(id),unit_cost_cents INTEGER,list_price_cents INTEGER,manufacturer_id INTEGER REFERENCES manufacturers(id));

CREATE TABLE purchase_lines(id INTEGER PRIMARY KEY,supplier_id INTEGER REFERENCES suppliers(id),product_id INTEGER REFERENCES products(id),warehouse_id INTEGER REFERENCES warehouses(id),ordered_qty INTEGER,received_qty INTEGER,po_date TEXT,expected_date TEXT,receipt_date TEXT);

CREATE TABLE quote_lines(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),product_id INTEGER REFERENCES products(id),quote_date TEXT,quantity INTEGER,unit_price_cents INTEGER,status TEXT);

CREATE TABLE service_events(id INTEGER PRIMARY KEY,order_line_id INTEGER REFERENCES order_lines(id),event_date TEXT,category TEXT,status TEXT);

CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT,country TEXT);

CREATE TABLE warehouses(id INTEGER PRIMARY KEY,name TEXT,region TEXT,country TEXT);
