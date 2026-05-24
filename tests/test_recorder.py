"""Tests for the record_usage pipeline (Candidate 1 deepening)."""

import pytest

from src.database import init_db
from src.database.usage import fetch_recent_usage


@pytest.fixture
def test_db(isolated_home):
    db_path = str(isolated_home / "usage.db")
    init_db(db_path)
    return db_path


def test_record_usage_inserts_row(test_db):
    from src.recorder import record_usage

    record_usage(
        ts=1779148800000000,
        provider="openai",
        model="gpt-4",
        client_source="test",
        session_id="sess-1",
        endpoint="/v1/chat/completions",
        prompt_tokens=100,
        completion_tokens=50,
        cached_tokens=0,
        total_tokens=150,
        reasoning_tokens=0,
        latency_ms=500,
        ttft_ms=None,
        status=200,
        db_path=test_db,
    )

    rows = fetch_recent_usage(limit=10, db_path=test_db)
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "openai"
    assert row["model"] == "gpt-4"
    assert row["prompt_tokens"] == 100
    assert row["completion_tokens"] == 50
    assert row["status"] == 200
    assert row["total_cost_usd"] is not None


def test_record_usage_computes_costs(test_db):
    from src import costs as costs_module
    from src.costs import ModelCost
    from src.recorder import record_usage

    original_model_costs = costs_module.MODEL_COSTS.copy()
    original_provider_costs = {
        provider: costs.copy()
        for provider, costs in costs_module.PROVIDER_MODEL_COSTS.items()
    }
    original_provider_map = costs_module.PROVIDER_MAP.copy()
    costs_module.MODEL_COSTS.clear()
    costs_module.PROVIDER_MODEL_COSTS.clear()
    costs_module.PROVIDER_MAP.clear()
    costs_module.MODEL_COSTS["test-model"] = ModelCost(
        input=1.0, output=2.0, cache_read=0.5
    )

    try:
        record_usage(
            provider="test-provider-without-override",
            model="test-model",
            client_source="test",
            session_id="sess-2",
            endpoint="/v1/chat/completions",
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=200,
            total_tokens=1500,
            reasoning_tokens=0,
            latency_ms=200,
            status=200,
            db_path=test_db,
        )

        rows = fetch_recent_usage(limit=10, db_path=test_db)
        assert len(rows) == 1
        row = rows[0]
        assert float(row["total_cost_usd"]) == pytest.approx(
            0.0008 + 0.0001 + 0.001, rel=1e-3
        )
    finally:
        costs_module.MODEL_COSTS.clear()
        costs_module.MODEL_COSTS.update(original_model_costs)
        costs_module.PROVIDER_MODEL_COSTS.clear()
        costs_module.PROVIDER_MODEL_COSTS.update(original_provider_costs)
        costs_module.PROVIDER_MAP.clear()
        costs_module.PROVIDER_MAP.update(original_provider_map)
