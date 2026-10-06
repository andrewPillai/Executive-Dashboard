"""Controlled natural-language analysis over the demo business database.

The first implementation is deliberately deterministic: it proves the query,
evidence, freshness and citation contract before an external model is enabled.
Set DATABASE_URL to PostgreSQL for the same read-only query catalog in production.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections import deque
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AI_RPM_LIMIT = 40
_ai_call_times: deque[float] = deque()
_ai_call_lock = threading.Lock()


class AIRateLimitError(RuntimeError):
    pass


def _consume_ai_slot() -> None:
    now = time.monotonic()
    with _ai_call_lock:
        while _ai_call_times and now - _ai_call_times[0] >= 60:
            _ai_call_times.popleft()
        if len(_ai_call_times) >= AI_RPM_LIMIT:
            raise AIRateLimitError("AI rate limit reached: maximum 40 provider calls per minute.")
        _ai_call_times.append(now)


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


def _model_answer(question: str, result: dict[str, Any]) -> str | None:
    """Ask an OpenAI-compatible provider to explain approved evidence.

    The model receives the deterministic answer and evidence rows only. It cannot
    issue SQL, select other records, or perform an operational write.
    """
    if result.get("intent") == "unsupported":
        return None
    providers = _provider_candidates()
    if not providers:
        return None
    payload = {
        "model": providers[0][1],
        "temperature": 0.2,
        "max_tokens": 500,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the executive operations assistant for a fictional company. "
                    "Explain only the approved evidence supplied by the application. "
                    "Do not invent facts, dates, causes, or totals. Do not claim to have "
                    "changed a system or assigned work. Write one concise management-ready "
                    "answer in plain text, with the conclusion first and a brief explanation. "
                    "Never mention prompts, approved_analysis, evidence formatting, or your reasoning."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "approved_analysis": result.get("answer", ""),
                        "intent": result.get("intent", ""),
                        "evidence": result.get("evidence", []),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
    }
    for base_url, model, api_key in providers:
        try:
            _consume_ai_slot()
            payload["model"] = model
            request = urllib.request.Request(
                f"{base_url}/chat/completions", data=json.dumps(payload, default=str).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(content, list):
                content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            leaked = ("the user asks:", "approved_analysis:", "evidence:", "let's craft", "we need to answer")
            if isinstance(content, str) and content.strip() and not any(marker in content.lower() for marker in leaked):
                return content.strip()
        except AIRateLimitError:
            raise
        except (Exception,):
            # Provider failure is intentionally non-fatal. The deterministic,
            # database-backed answer remains the product fallback.
            continue
    return None


def _provider_candidates() -> list[tuple[str, str, str]]:
    """Return primary then optional backup OpenAI-compatible providers."""
    candidates = []
    primary_base = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
    primary_key = os.getenv("AI_API_KEY", "").strip()
    for prefix in ("AI", "AI_FALLBACK"):
        base_url = os.getenv(f"{prefix}_BASE_URL", "").strip().rstrip("/") or (primary_base if prefix == "AI_FALLBACK" else "")
        model = os.getenv(f"{prefix}_MODEL", "").strip()
        api_key = os.getenv(f"{prefix}_API_KEY", "").strip() or (primary_key if prefix == "AI_FALLBACK" else "")
        if base_url and model and api_key and (base_url, model, api_key) not in candidates:
            candidates.append((base_url, model, api_key))
    return candidates

_ALLOWED_TABLES = {
    "customers", "manufacturers", "suppliers", "warehouses", "products", "orders",
    "order_lines", "invoice_lines", "purchase_lines", "inventory_balances",
    "inventory_movements", "service_events", "pricing_records", "direct_fulfillment",
}
_FORBIDDEN_SQL = ("insert", "update", "delete", "drop", "alter", "create", "replace", "truncate", "attach", "detach", "pragma", "copy", "vacuum")


def _validated_select(sql: str) -> str:
    sql = sql.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    lowered = sql.lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise ValueError("The advanced analysis did not produce a read-only query.")
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("The advanced analysis query was rejected by the read-only guard.")
    if any(__import__("re").search(rf"\b{word}\b", lowered) for word in _FORBIDDEN_SQL):
        raise ValueError("The advanced analysis query was rejected by the read-only guard.")
    import re
    tables = set(re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", lowered))
    if not tables or not tables.issubset(_ALLOWED_TABLES):
        raise ValueError("The advanced analysis referenced an unsupported business table.")
    limits = re.findall(r"\blimit\s+(\d+)", lowered)
    if limits and int(limits[-1]) > 100:
        raise ValueError("The advanced analysis result is limited to 100 rows.")
    return sql if limits else f"{sql} LIMIT 100"


def _model_sql(question: str) -> str:
    providers = _provider_candidates()
    if not providers:
        raise RuntimeError("Advanced analysis needs the configured AI provider.")
    schema = ", ".join(sorted(_ALLOWED_TABLES))
    payload = {
        "model": providers[0][1],
        "temperature": 0,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": (
                "Generate one read-only SQL query for the fictional operations database. "
                "Return JSON only with a single sql field. Use only these tables: " + schema + ". "
                "Use SELECT or WITH, never writes, never comments, never multiple statements, "
                "and return a useful aggregate or detail result. The server will validate the query."
            )},
            {"role": "user", "content": question},
        ],
    }
    for base_url, model, api_key in providers:
        try:
            _consume_ai_slot()
            payload["model"] = model
            request = urllib.request.Request(
                f"{base_url}/chat/completions", data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(content, list):
                content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            content = str(content).strip().removeprefix("```json").removesuffix("```").strip()
            return str(json.loads(content)["sql"])
        except AIRateLimitError:
            raise
        except (Exception,):
            continue
    raise RuntimeError("The AI provider could not produce a safe read-only analysis.")


def _audience_next_step(intent: str, audience: str, default: str) -> str:
    focus = {
        "sales": "Sales: review the affected customer commitments, requested dates, and recovery options with Operations.",
        "commercial": "Commercial: review customer, product, and pricing impact before changing a commitment or price.",
        "customer": "Customer: open the affected accounts and prepare the customer communication and service follow-up.",
        "operations": "Operations: review stock, fulfillment capacity, and supplier dependencies before coordinating recovery.",
        "planning": "Planning: compare supply, inventory, and replenishment options against the customer impact.",
        "finance": "Finance: quantify the revenue, margin, and working-capital exposure before approving a response.",
        "analytics": "Analytics: validate the evidence across source records and monitor the trend behind this exception.",
    }
    return focus.get(audience.lower(), default)


def advanced_answer(question: str, data_dir: Path, audience: str = "executive") -> dict[str, Any]:
    try:
        sql = _validated_select(_model_sql(question.strip()))
    except AIRateLimitError:
        raise
    except (RuntimeError, ValueError):
        # A model outage must not block common operational questions that are
        # already covered by the approved catalog.
        fallback = _catalog_answer(question, data_dir, audience)
        fallback["next_step"] = _audience_next_step(fallback.get("intent", ""), audience, fallback.get("next_step", ""))
        fallback["advanced"] = False
        fallback["ai_provider"] = None
        fallback["ai_model"] = None
        return fallback
    db, source = _connect(data_dir)
    try:
        rows = _query(db, sql)
        result = {
            "source": source, "freshness": datetime.now(timezone.utc).isoformat(), "question": question.strip(),
            "intent": "advanced_read_only", "answer": f"The read-only analysis returned {len(rows):,} evidence rows.",
            "evidence": rows, "next_step": "Review the evidence and open the related records before drafting any human-approved action.",
            "sql": sql,
        }
        result["next_step"] = _audience_next_step("advanced_read_only", audience, result["next_step"])
        model_text = _model_answer(question.strip(), result)
        if model_text:
            result["answer"] = model_text
        result["ai_model"] = os.getenv("AI_MODEL", "").strip()
        result["advanced"] = True
        return result
    finally:
        db.close()

def _catalog_answer(question: str, data_dir: Path, audience: str = "executive") -> dict[str, Any]:
    q = question.strip()
    if not q:
        raise ValueError("Ask a question about customers, orders, delivery, inventory, margin, or revenue.")
    lowered = q.lower()
    db, source = _connect(data_dir)
    try:
        common = {"source": source, "freshness": datetime.now(timezone.utc).isoformat(), "question": q, "audience": audience}
        if ("highest" in lowered or "most" in lowered or "top" in lowered) and ("ordered" in lowered or "order" in lowered) and ("product" in lowered or "unit" in lowered or "quantity" in lowered):
            rows = _query(db, """select cu.id customer_id, cu.name customer,
                sum(l.ordered_qty) ordered_units, count(distinct l.product_id) distinct_products,
                count(distinct o.id) orders
                from order_lines l join orders o on o.id=l.order_id join customers cu on cu.id=o.customer_id
                group by cu.id, cu.name order by ordered_units desc limit 20""")
            leader = rows[0] if rows else None
            lead_text = f"{leader['customer']} ordered the highest volume at {int(leader['ordered_units']):,} units across {leader['distinct_products']:,} products." if leader else "No ordered product volume was found in the current snapshot."
            return {**common, "intent": "top_customer_volume", "answer": lead_text, "evidence": rows, "next_step": "Open the customer profile to review product mix, open commitments, and delivery status."}
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


def answer(question: str, data_dir: Path, audience: str = "executive") -> dict[str, Any]:
    result = _catalog_answer(question, data_dir, audience)
    result["next_step"] = _audience_next_step(result.get("intent", ""), audience, result.get("next_step", ""))
    model_text = _model_answer(question.strip(), result)
    if model_text:
        result = {**result, "answer": model_text, "ai_provider": os.getenv("AI_BASE_URL", "").strip(), "ai_model": os.getenv("AI_MODEL", "").strip()}
    else:
        result = {**result, "ai_provider": None, "ai_model": None}
    return result
