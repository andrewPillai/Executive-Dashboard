"""Controlled natural-language analysis over the demo business database.

The first implementation is deliberately deterministic: it proves the query,
evidence, freshness and citation contract before an external model is enabled.
Set DATABASE_URL to PostgreSQL for the same read-only query catalog in production.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _connect(data_dir: Path):
    url = os.getenv("DATABASE_URL")
    if url:
        try:
            import psycopg
            return psycopg.connect(url, connect_timeout=5), "postgresql"
        except Exception as exc:
            raise RuntimeError(f"PostgreSQL is configured but unavailable: {exc}") from exc
    return sqlite3.connect((data_dir / "northstar.sqlite").resolve().as_uri() + "?mode=ro", uri=True), "sqlite"


def _one(db, sql: str) -> Any:
    row = db.execute(sql).fetchone()
    return row[0] if row else 0


def _query(db, sql: str):
    cur = db.execute(sql)
    names = [x[0] for x in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def answer(question: str, data_dir: Path) -> dict[str, Any]:
    q = question.strip()
    if not q:
        raise ValueError("Ask a question about customers, orders, delivery, inventory, margin, or revenue.")
    lowered = q.lower()
    db, source = _connect(data_dir)
    try:
        common = {"source": source, "freshness": datetime.now(timezone.utc).isoformat(), "question": q}
        if any(word in lowered for word in ("commitment", "commitments", "at risk", "customer order")):
            rows = _query(db, """select cu.id customer_id, cu.name customer, count(*) open_lines,
                round(sum((l.ordered_qty-l.delivered_qty)*l.unit_price_cents)/100.0,2) exposure_usd
                from order_lines l join orders o on o.id=l.order_id join customers cu on cu.id=o.customer_id
                where l.delivered_qty < l.ordered_qty group by cu.id, cu.name order by exposure_usd desc limit 20""")
            total = _one(db, "select round(sum((ordered_qty-delivered_qty)*unit_price_cents)/100.0,2) from order_lines where delivered_qty < ordered_qty")
            return {**common, "intent": "customer_commitments", "answer": f"{total:,.2f} USD is tied to incomplete customer commitments. The highest exposures are listed below.", "evidence": rows, "next_step": "Open the highest exposure customer and review requested dates, stock, and supplier dependencies."}
        if any(word in lowered for word in ("coordinate", "coordination", "cross-department", "between sales", "between operations")):
            rows = _query(db, """select scenario_id, count(*) lines, round(sum((ordered_qty-shipped_qty)*unit_price_cents)/100.0,2) open_value_usd
                from order_lines where scenario_id is not null group by scenario_id order by open_value_usd desc""")
            return {**common, "intent": "coordination", "answer": "These seeded scenarios require coordination across commercial and operating teams.", "evidence": rows, "next_step": "Open a scenario to draft a human-approved response and assign dependencies."}
        if any(word in lowered for word in ("revenue", "sales", "threat")):
            rows = _query(db, """select o.region, round(sum((l.ordered_qty-l.delivered_qty)*l.unit_price_cents)/100.0,2) exposure_usd,
                count(*) open_lines from order_lines l join orders o on o.id=l.order_id
                where l.delivered_qty < l.ordered_qty group by o.region order by exposure_usd desc""")
            total = _one(db, "select round(sum((ordered_qty-delivered_qty)*unit_price_cents)/100.0,2) from order_lines where delivered_qty < ordered_qty")
            return {**common, "intent": "revenue_exposure", "answer": f"{total:,.2f} USD of open order value is exposed across incomplete commitments.", "evidence": rows, "next_step": "Prioritize overdue lines by customer requested date and local stock."}
        if "on-time" in lowered or "otif" in lowered or "delivery" in lowered or "late" in lowered:
            result = _one(db, "select round(100.0 * sum(case when delivered_qty >= ordered_qty and delivered_date <= requested_date then 1 else 0 end) / nullif(sum(case when delivered_qty > 0 then 1 else 0 end),0),1) from order_lines")
            rows = _query(db, """select fulfillment_mode, count(*) lines, sum(case when delivered_qty < ordered_qty then 1 else 0 end) incomplete
                from order_lines group by fulfillment_mode order by incomplete desc""")
            return {**common, "intent": "delivery_performance", "answer": f"The synthetic delivery rate is {float(result or 0):.1f}% under the demo OTIF definition.", "evidence": rows, "next_step": "Inspect incomplete lines by fulfillment mode, requested date, and supply exception."}
        if "inventory" in lowered or "reposition" in lowered or "stock" in lowered:
            rows = _query(db, """select w.name warehouse, count(*) shortage_products, round(sum(case when b.on_hand_qty < 0 then abs(b.on_hand_qty) else 0 end),0) shortage_units
                from inventory_balances b join warehouses w on w.id=b.warehouse_id where b.on_hand_qty <= 0 group by w.name order by shortage_units desc limit 10""")
            return {**common, "intent": "inventory_risk", "answer": "These locations have the strongest shortage signal in the current synthetic snapshot.", "evidence": rows, "next_step": "Compare shortage locations with surplus stock before proposing a transfer."}
        if "margin" in lowered or "profit" in lowered or "pricing" in lowered:
            rows = _query(db, """select o.region, round(sum((l.unit_price_cents-l.unit_cost_cents)*l.delivered_qty)/100.0,2) gross_profit_usd,
                round(sum(l.delivered_qty*l.unit_price_cents)/100.0,2) sales_usd from order_lines l join orders o on o.id=l.order_id
                where l.delivered_qty > 0 group by o.region order by gross_profit_usd asc""")
            return {**common, "intent": "margin", "answer": "Gross profit is shown by customer region so the weakest contribution can be investigated next.", "evidence": rows, "next_step": "Open the affected product and customer cohorts before changing price."}
        if "expedite" in lowered or "purchase order" in lowered or "supplier" in lowered:
            rows = _query(db, """select p.id, p.product_id, p.ordered_qty, p.received_qty, p.expected_date
                from purchase_lines p where p.received_qty < p.ordered_qty order by p.expected_date limit 10""")
            return {**common, "intent": "supplier_expedite", "answer": "The following open purchase lines are candidates for an expedite scenario.", "evidence": rows, "next_step": "A future scenario tool will model expedite cost, date improvement, and customer impact before approval."}
        return {**common, "intent": "unsupported", "answer": "I can analyze the connected synthetic data, but this question needs a defined business metric or source field before I can answer it reliably.", "evidence": [], "next_step": "Try asking about revenue, commitments, delivery, inventory, margin, suppliers, or coordination."}
    finally:
        db.close()
