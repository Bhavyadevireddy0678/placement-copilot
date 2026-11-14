from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

import ask_api


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [
            {"company": "Amazon", "placement_count": 49, "average_package": 16.97},
            {"company": "Google", "placement_count": 51, "average_package": 29.25},
        ]


class FakeConnection:
    def execute(self, query):
        assert "GROUP BY company" in str(query)
        return FakeResult()


class FakeEngine:
    def connect(self):
        return self

    def __enter__(self):
        return FakeConnection()

    def __exit__(self, *_args):
        return False


def test_company_summaries_returns_aggregated_values(monkeypatch):
    monkeypatch.setattr(ask_api, "sql_engine", FakeEngine())

    response = ask_api.company_summaries()

    assert response["sample_data"] is True
    assert response["companies"][0]["placement_count"] == 49
    assert response["companies"][1]["average_package"] == 29.25


def test_company_summaries_returns_503_on_database_failure(monkeypatch):
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("database failure")

    monkeypatch.setattr(ask_api, "sql_engine", BrokenEngine())
    with pytest.raises(HTTPException) as error:
        ask_api.company_summaries()
    assert error.value.status_code == 503


def test_static_company_profiles_are_data_driven_and_labeled():
    base_dir = Path(__file__).resolve().parent
    html = (base_dir / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (base_dir / "static" / "app.js").read_text(encoding="utf-8")

    assert "companyGrid" in html
    assert "Sample placement data" in html
    assert "124 students" not in html
    assert "48 students" not in html
    assert "26 students" not in html
    assert "fetch('/company-summaries')" in javascript
    assert "meta.textContent" in javascript
