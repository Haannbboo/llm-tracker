"""Shared model identity across price imports, overrides, and lookups."""

from decimal import Decimal


def test_price_sources_use_shared_model_names():
    from src.pricing.sources.litellm import _parse_litellm_json
    from src.pricing.sources.openrouter import parse_openrouter_json

    litellm = _parse_litellm_json(
        {
            " Space-Bunny-Free ": {
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            }
        }
    )
    openrouter = parse_openrouter_json(
        {
            "data": [
                {
                    "id": " Space-Bunny-Free ",
                    "pricing": {"prompt": "0", "completion": "0"},
                }
            ]
        }
    )
    assert set(litellm) == {"stealth/space-bunny-alpha"}
    assert "stealth/space-bunny-alpha" in openrouter
    assert "space-bunny-free" not in openrouter


def test_aliases_preserve_price_override_precedence():
    from src.pricing.costs import resolve_cost_match
    from src.pricing.maps import resolve_all_costs
    from src.pricing.models import ModelCost
    from src.pricing.sources.base import FetchedSource, SourceEntry

    resolved = resolve_all_costs(
        {
            "models": {
                " STEALTH/SPACE-BUNNY-ALPHA ": {"cost": {"input": 1, "output": 2}}
            },
            "providers": {
                "custom": {"models": {"Space-Bunny-Free": {"cost": {"output": 3}}}}
            },
        },
        [
            FetchedSource(
                name="test-source",
                priority=10,
                entries=(
                    SourceEntry(
                        provider=None,
                        key=" Space-Bunny-Free ",
                        cost=ModelCost(input=0, output=0, cache_read=0.5),
                    ),
                ),
            )
        ],
    )
    key = "stealth/space-bunny-alpha"
    assert set(resolved.global_costs) == {key}
    assert set(resolved.provider_costs["custom"]) == {key}
    global_costs = {key: rc.cost for key, rc in resolved.global_costs.items()}
    provider_costs = {
        provider: {key: rc.cost for key, rc in costs.items()}
        for provider, costs in resolved.provider_costs.items()
    }
    for name in ("Space-Bunny-Free", " STEALTH/SPACE-BUNNY-ALPHA "):
        match = resolve_cost_match("custom", name, global_costs, provider_costs)
        assert match is not None
        assert (match.key, match.scope, match.source) == (key, "provider", "yaml")
        assert match.cost == ModelCost(input=1, output=3, cache_read=0.5)

        match = resolve_cost_match(None, name, global_costs, provider_costs)
        assert match is not None
        assert (match.key, match.scope) == (key, "global")
        assert match.cost == ModelCost(input=1, output=2, cache_read=0.5)


def test_unmapped_free_name_has_no_cost():
    from src.pricing.costs import calculate_costs, resolve_pricing
    from src.pricing.models import ModelCost

    costs = {"deepseek-v4.1-flash": ModelCost(input=1, output=2, cache_read=0)}
    resolved = resolve_pricing(
        None, "deepseek-v4.1-flash-free", 1779148800000000, costs, {}
    )
    assert resolved.match is None
    assert calculate_costs(
        prompt_tokens=100,
        completion_tokens=50,
        cached_tokens=0,
        model_cost=resolved.cost,
    )["total_cost_usd"] == Decimal("0")


def test_snapshot_enrichment_resolves_alias(fresh_db):
    from src.pricing.models import ModelCost
    from src.pricing.snapshots import enrich_rows, ensure_price_snapshot

    ensure_price_snapshot(
        date="2026-05-19",
        provider="custom",
        model="stealth/space-bunny-alpha",
        source="yaml",
        cost=ModelCost(input=1, output=2, cache_read=0),
        multiplier=Decimal("1"),
        db_path=fresh_db.db_path,
    )
    row = enrich_rows(
        [
            {
                "ts": 1779148800000000,
                "provider": "custom",
                "model": " Space-Bunny-Free ",
                "prompt_tokens": 1000,
            }
        ],
        db_path=fresh_db.db_path,
    )[0]
    assert row["normal_input_cost_usd"] == 0.001
    assert row["pricing"]["source"] == "yaml"


def test_legacy_cost_key_export_uses_shared_normalizer():
    from src.pricing.models import normalize_model_cost_key
    from src.utils import normalize_model_name

    assert normalize_model_cost_key is normalize_model_name
