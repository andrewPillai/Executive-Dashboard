from pathlib import Path
import time
import urllib.error

from fastapi.testclient import TestClient

from backend.main import create_app
from backend import questioning


def test_question_catalog_answers_supported_questions(tmp_path: Path):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    for question, intent in [
        ("What threatens revenue this week?", "revenue_exposure"),
        ("Which customer commitments are at risk?", "customer_commitments"),
        ("Why is on-time delivery below target?", "delivery_performance"),
        ("Which inventory should be repositioned?", "inventory_risk"),
        ("Show me margin erosion by customer and product.", "margin"),
        ("What should we coordinate between Sales and Operations?", "coordination"),
        ("What happens if we expedite the delayed purchase order?", "supplier_expedite"),
    ]:
        response = client.post("/api/ask", json={"question": question})
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == intent
        assert body["evidence"]
        assert body["freshness"]


def test_question_catalog_does_not_invent_unsupported_answers(tmp_path: Path):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    response = TestClient(app).post("/api/ask", json={"question": "What is our accounts receivable aging?"})
    assert response.status_code == 200
    assert response.json()["intent"] == "unsupported"


def test_audience_is_returned_and_changes_next_step(tmp_path: Path):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    sales = client.post("/api/ask", json={"question": "Which customer commitments are at risk?", "audience": "sales"}).json()
    finance = client.post("/api/ask", json={"question": "Which customer commitments are at risk?", "audience": "finance"}).json()
    assert sales["audience"] == "sales"
    assert finance["audience"] == "finance"
    assert sales["next_step"] != finance["next_step"]


def test_provider_failure_returns_deterministic_answer(tmp_path: Path, monkeypatch):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    monkeypatch.setenv("AI_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "primary")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setattr(questioning.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    response = client.post("/api/ask", json={"question": "What threatens revenue this week?"})
    assert response.status_code == 200
    assert response.json()["ai_model"] is None
    assert response.json()["intent"] == "revenue_exposure"


def test_rate_limit_returns_429(tmp_path: Path, monkeypatch):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    monkeypatch.setenv("AI_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "primary")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    with questioning._ai_call_lock:
        questioning._ai_call_times.clear()
        questioning._ai_call_times.extend([time.monotonic()] * questioning.AI_RPM_LIMIT)
    try:
        response = client.post("/api/ask", json={"question": "What threatens revenue this week?"})
        assert response.status_code == 429
    finally:
        with questioning._ai_call_lock:
            questioning._ai_call_times.clear()


def test_advanced_rejected_sql_falls_back_to_catalog(tmp_path: Path, monkeypatch):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    monkeypatch.setattr(questioning, "_model_sql", lambda question: "DELETE FROM orders")
    response = client.post("/api/ask/advanced", json={"question": "Which customer commitments are at risk?", "audience": "operations"})
    assert response.status_code == 200
    body = response.json()
    assert body["advanced"] is False
    assert body["intent"] == "customer_commitments"
    assert body["audience"] == "operations"


def test_sql_guard_rejects_writes_and_unknown_tables():
    for sql in ("DELETE FROM orders", "SELECT * FROM secrets", "SELECT * FROM orders; DROP TABLE orders"):
        try:
            questioning._validated_select(sql)
        except ValueError:
            continue
        raise AssertionError(f"unsafe SQL was accepted: {sql}")
