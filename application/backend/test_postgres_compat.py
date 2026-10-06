"""Production-dialect smoke tests.

These tests are skipped locally unless DATABASE_URL points at an isolated
PostgreSQL test database. CI or a release operator should set that variable
after the synthetic schema has been migrated; the live production database is
never used as a test target.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires an isolated PostgreSQL test database")
def test_department_workbenches_run_on_postgresql(tmp_path: Path):
    app = create_app(data_dir=Path(__file__).parents[1] / "data", workflow_path=tmp_path / "workflow.sqlite")
    client = TestClient(app)
    for role in ("executive", "sales", "commercial", "service", "operations", "planning", "finance", "analytics"):
        response = client.get(f"/api/departments/{role}")
        assert response.status_code == 200, response.text
        assert response.json()["metrics"]
