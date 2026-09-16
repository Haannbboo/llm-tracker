"""Config-driven cache TTL for price sources.

Covers the three layers that make ``pricing.sources[].ttl_seconds`` effective:
the generic cache helpers, the OpenRouter source's fetch gate, and the registry
that maps config onto the source constructor.
"""

from __future__ import annotations

import json
import os
import time

import pytest

_OPENROUTER_PAYLOAD = {
    "data": [
        {
            "id": "vendor/model-a",
            "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        }
    ]
}


def _age(path, seconds: float) -> None:
    mtime = time.time() - seconds
    os.utime(path, (mtime, mtime))


def test_cache_is_fresh_respects_ttl(load_module):
    base = load_module("src.pricing.sources.base")
    path = base.cache_path("demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")

    assert base.cache_is_fresh("demo", 3600) is True

    _age(path, 7200)
    assert base.cache_is_fresh("demo", 3600) is False
    # Non-positive TTL always means "stale", even with a just-written file.
    assert base.cache_is_fresh("demo", 0) is False
    # Missing file is never fresh.
    assert base.cache_is_fresh("missing", 3600) is False


def test_openrouter_source_uses_fresh_cache(load_module, monkeypatch):
    openrouter = load_module("src.pricing.sources.openrouter")
    base = load_module("src.pricing.sources.base")
    base.save_cache_json("openrouter", _OPENROUTER_PAYLOAD)

    def _fail():
        raise AssertionError("network must not be hit for a fresh cache")

    monkeypatch.setattr(openrouter, "_fetch_openrouter_json", _fail)

    entries = openrouter.OpenRouterSource(ttl_seconds=3600).fetch()

    assert "vendor/model-a" in {entry.key for entry in entries}


def test_openrouter_source_refetches_when_cache_stale(load_module, monkeypatch):
    openrouter = load_module("src.pricing.sources.openrouter")
    base = load_module("src.pricing.sources.base")
    base.save_cache_json(
        "openrouter",
        {"data": [{"id": "vendor/old", "pricing": {"prompt": "1", "completion": "1"}}]},
    )
    path = base.cache_path("openrouter")
    _age(path, 7 * 3600)

    monkeypatch.setattr(
        openrouter, "_fetch_openrouter_json", lambda: _OPENROUTER_PAYLOAD
    )

    entries = openrouter.OpenRouterSource(ttl_seconds=3600).fetch()

    assert "vendor/model-a" in {entry.key for entry in entries}
    # The freshly fetched payload replaced the stale cache on disk.
    assert json.loads(path.read_text()) == _OPENROUTER_PAYLOAD


def test_openrouter_source_ttl_zero_always_refetches(load_module, monkeypatch):
    openrouter = load_module("src.pricing.sources.openrouter")
    base = load_module("src.pricing.sources.base")
    base.save_cache_json(
        "openrouter",
        {"data": [{"id": "vendor/old", "pricing": {"prompt": "1", "completion": "1"}}]},
    )

    called = []
    monkeypatch.setattr(
        openrouter,
        "_fetch_openrouter_json",
        lambda: called.append(True) or _OPENROUTER_PAYLOAD,
    )

    entries = openrouter.OpenRouterSource(ttl_seconds=0).fetch()

    assert called == [True]
    assert "vendor/model-a" in {entry.key for entry in entries}


def test_litellm_source_uses_config_ttl(load_module, monkeypatch):
    litellm = load_module("src.pricing.sources.litellm")
    base = load_module("src.pricing.sources.base")
    cache_path = base.cache_path(litellm.CACHE_NAME)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"gpt-fresh": {"input_cost_per_token": 1e-06, "mode": "chat"}})
    )
    monkeypatch.setattr(litellm, "_remote_costs", None)

    def _fail():
        raise AssertionError("network must not be hit for a fresh cache")

    monkeypatch.setattr(litellm, "_fetch_litellm_json", _fail)

    entries = litellm.LiteLLMSource(ttl_seconds=3600).fetch()

    assert "gpt-fresh" in {entry.key for entry in entries}


def test_litellm_source_refetches_when_stale(load_module, monkeypatch):
    litellm = load_module("src.pricing.sources.litellm")
    base = load_module("src.pricing.sources.base")
    cache_path = base.cache_path(litellm.CACHE_NAME)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"gpt-old": {"input_cost_per_token": 1e-06, "mode": "chat"}})
    )
    _age(cache_path, 7 * 3600)
    monkeypatch.setattr(litellm, "_remote_costs", None)
    monkeypatch.setattr(
        litellm,
        "_fetch_litellm_json",
        lambda: {"gpt-new": {"input_cost_per_token": 2e-06, "mode": "chat"}},
    )

    entries = litellm.LiteLLMSource(ttl_seconds=3600).fetch()

    keys = {entry.key for entry in entries}
    assert "gpt-new" in keys
    assert "gpt-old" not in keys
    assert "gpt-new" in json.loads(cache_path.read_text())


def test_registry_applies_configured_ttl(load_module):
    registry = load_module("src.pricing.sources.registry")
    sources = registry.build_sources(
        {
            "pricing": {
                "sources": [
                    {"name": "openrouter", "type": "openrouter", "ttl_seconds": 1234},
                    {"name": "litellm", "type": "litellm", "ttl_seconds": 900},
                ]
            }
        }
    )

    assert [source.ttl_seconds for source in sources] == [1234, 900]


def test_registry_defaults_ttl_when_absent_or_invalid(load_module):
    registry = load_module("src.pricing.sources.registry")
    openrouter = load_module("src.pricing.sources.openrouter")
    litellm = load_module("src.pricing.sources.litellm")

    for source_type, default in (
        ("openrouter", openrouter.DEFAULT_TTL_SECONDS),
        ("litellm", litellm.CACHE_TTL_SECONDS),
    ):
        for spec in (
            {"name": source_type, "type": source_type},
            {"name": source_type, "type": source_type, "ttl_seconds": "nonsense"},
        ):
            sources = registry.build_sources({"pricing": {"sources": [spec]}})
            assert sources[0].ttl_seconds == default


def test_cache_path_rejects_unsafe_names(load_module):
    base = load_module("src.pricing.sources.base")

    for bad in ("../config", "a/b", ".", "..", "", "-flag"):
        with pytest.raises(ValueError):
            base.cache_path(bad)

    assert base.cache_path("openrouter").name == "openrouter.json"
