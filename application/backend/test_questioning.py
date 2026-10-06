from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app


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
