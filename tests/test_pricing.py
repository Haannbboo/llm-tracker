from __future__ import annotations

import json
import os
import time
import urllib.error

from fastapi.testclient import TestClient

import config.pricing as pricing_module
from config.app import ModelCost, ModelTier
from config.pricing import (
    _claude_3x_alias,
    _is_chat_model,
    _parse_litellm_json,
    _parse_model_entry,
    _strip_provider_prefix,
    _strip_version_suffix,
    fetch_remote_pricing,
)

# --- Key normalization ---


def test_strip_provider_prefix_anthropic():
    assert _strip_provider_prefix("anthropic.claude-sonnet-4-5-20250929-v1:0") == (
        "claude-sonnet-4-5-20250929-v1:0"
    )


def test_strip_provider_prefix_azure_ai():
    assert _strip_provider_prefix("azure_ai/gpt-5.4") == "gpt-5.4"


def test_strip_provider_prefix_bedrock():
    assert (
        _strip_provider_prefix(
            "bedrock_converse.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
        == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    )


def test_strip_provider_prefix_vertex():
    assert _strip_provider_prefix("vertex_ai/gemini-2.5-pro") == "gemini-2.5-pro"


def test_strip_provider_prefix_noop():
    assert _strip_provider_prefix("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_strip_version_suffix_date():
    assert _strip_version_suffix("claude-sonnet-4-5-20250929") == "claude-sonnet-4-5"


def test_strip_version_suffix_iso_date():
    assert _strip_version_suffix("gpt-4o-2024-08-06") == "gpt-4o"


def test_strip_version_suffix_noop():
    assert _strip_version_suffix("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_strip_version_suffix_with_v_suffix():
    assert (
        _strip_version_suffix("claude-sonnet-4-5-20250929-v1:0") == "claude-sonnet-4-5"
    )


# --- Model entry parsing ---


def test_parse_model_cost_with_cache_write(config_module):
    model_config = {
        "cost": {
            "input": 3.0,
            "output": 15.0,
            "cacheRead": 0.3,
            "cacheWrite": 3.75,
        }
    }

    cost = config_module._parse_model_cost(model_config)

    assert cost is not None
    assert cost.cache_write == 3.75


def test_parse_model_cost_without_cache_write(config_module):
    model_config = {"cost": {"input": 3.0, "output": 15.0, "cacheRead": 0.3}}

    cost = config_module._parse_model_cost(model_config)

    assert cost is not None
    assert cost.cache_write is None


def test_parse_model_cost_with_tiers(config_module):
    model_config = {
        "cost": {
            "tiers": [
                {"range": [0, 256000], "input": 0.4, "output": 1.6, "cacheRead": 0.08},
                {"range": [256000, 1000000], "input": 1.2, "output": 4.8},
            ]
        }
    }

    cost = config_module._parse_model_cost(model_config)

    assert cost is not None
    assert len(cost.tiers) == 2
    first, second = cost.tiers
    assert first.min_tokens == 0
    assert first.max_tokens == 256000
    assert first.input == 0.4
    assert first.output == 1.6
    assert first.cache_read == 0.08
    assert second.input == 1.2
    assert second.cache_read == 0.08  # falls back to first-tier flat price
    # Flat prices default to the first tier when not specified
    assert cost.input == 0.4
    assert cost.output == 1.6


def test_parse_model_cost_with_tiers_inherits_flat_from_yaml(config_module):
    model_config = {
        "cost": {
            "input": 3.0,
            "output": 15.0,
            "cacheRead": 0.3,
            "tiers": [
                {"range": [0, 100000], "input": 1.0, "output": 5.0},
                {"range": [100000, None], "input": 2.0, "output": 10.0},
            ],
        }
    }

    cost = config_module._parse_model_cost(model_config)

    assert cost is not None
    assert cost.input == 3.0
    assert cost.output == 15.0
    assert cost.tiers[0].cache_read == 0.3
    assert cost.tiers[1].max_tokens is None


def test_parse_model_cost_without_tiers_inherits_base_tiers(config_module):
    base = config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        tiers=(
            config_module.ModelTier(
                min_tokens=0, max_tokens=256000, input=0.4, output=1.6, cache_read=0.08
            ),
        ),
    )
    # No flat prices and no tiers key: keep the base's tiered pricing.
    model_config = {"cost": {"cacheWrite": 3.0}}

    cost = config_module._parse_model_cost(model_config, base)

    assert cost is not None
    assert cost.tiers == base.tiers
    assert cost.cache_write == 3.0
    assert cost.input == 0.4


def test_parse_model_cost_flat_prices_clear_inherited_tiers(config_module):
    base = config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        tiers=(
            config_module.ModelTier(
                min_tokens=0, max_tokens=256000, input=0.4, output=1.6, cache_read=0.08
            ),
        ),
    )
    # Explicit flat prices are an override: tiers must not silently win.
    model_config = {"cost": {"input": 3.0, "output": 15.0}}

    cost = config_module._parse_model_cost(model_config, base)

    assert cost is not None
    assert cost.tiers == ()
    assert cost.input == 3.0
    assert cost.output == 15.0


def test_parse_model_cost_empty_tiers_disables_tiers(config_module):
    base = config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        tiers=(
            config_module.ModelTier(
                min_tokens=0, max_tokens=256000, input=0.4, output=1.6, cache_read=0.08
            ),
        ),
    )
    model_config = {"cost": {"tiers": []}}

    cost = config_module._parse_model_cost(model_config, base)

    assert cost is not None
    assert cost.tiers == ()
    assert cost.input == 0.4


def test_parse_model_cost_skips_malformed_tiers(config_module):
    model_config = {
        "cost": {
            "tiers": [
                {"range": [None, 1000], "input": 1.0, "output": 2.0},
                {"range": ["bad", "worse"], "input": 1.0, "output": 2.0},
                {"range": [0, 256000], "input": "not-a-number", "output": 2.0},
                {"range": [256000, None], "input": 1.2, "output": 4.8},
            ]
        }
    }

    cost = config_module._parse_model_cost(model_config)

    assert cost is not None
    assert len(cost.tiers) == 1
    assert cost.tiers[0].min_tokens == 256000


def test_apply_patch_set_creates_nested_dicts_with_literal_keys(config_module):
    config = {"models": {}}

    config_module._apply_patch(
        config,
        ["models", "vendor/model.v1", "cost", "cacheRead"],
        "set",
        0.25,
    )

    assert config["models"]["vendor/model.v1"]["cost"]["cacheRead"] == 0.25


def test_apply_patch_delete_missing_leaf_is_noop(config_module):
    config = {"models": {"test-model": {"cost": {"input": 1.0}}}}

    config_module._apply_patch(
        config,
        ["models", "test-model", "cost", "cacheRead"],
        "delete",
        None,
    )

    assert config == {"models": {"test-model": {"cost": {"input": 1.0}}}}


def test_apply_patch_delete_missing_nested_path_is_noop(config_module):
    config = {"models": {}}

    config_module._apply_patch(
        config,
        ["models", "missing-model", "cost", "input"],
        "delete",
        None,
    )

    assert config == {"models": {}}


def test_is_chat_model_chat_mode():
    assert _is_chat_model({"mode": "chat"}) is True


def test_is_chat_model_text_mode():
    assert _is_chat_model({"mode": "text"}) is True


def test_is_chat_model_default():
    assert _is_chat_model({}) is True


def test_is_chat_model_image():
    assert _is_chat_model({"mode": "image_generation"}) is False


def test_is_chat_model_embedding():
    assert _is_chat_model({"mode": "embedding"}) is False


def test_is_chat_model_responses():
    assert _is_chat_model({"mode": "responses"}) is True


def test_parse_model_entry_converts_per_token_to_per_million():
    entry = {
        "mode": "chat",
        "input_cost_per_token": 3e-06,
        "output_cost_per_token": 1.5e-05,
        "cache_read_input_token_cost": 3e-07,
    }
    result = _parse_model_entry("anthropic.claude-sonnet-4-5-20250929-v1:0", entry)

    assert result is not None
    key, cost = result
    assert key == "claude-sonnet-4-5-20250929-v1:0"
    assert cost.input == 3.0  # 3e-06 * 1M
    assert cost.output == 15.0  # 1.5e-05 * 1M
    assert cost.cache_read == 0.3  # 3e-07 * 1M


def test_parse_model_entry_no_cache_read():
    entry = {
        "mode": "chat",
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1.5e-05,
    }
    result = _parse_model_entry("azure_ai/gpt-5.4", entry)

    assert result is not None
    _, cost = result
    assert cost.cache_read == 0.0


def test_parse_model_entry_responses_with_cache_read():
    entry = {
        "mode": "responses",
        "input_cost_per_token": 1.25e-06,
        "output_cost_per_token": 1e-05,
        "cache_read_input_token_cost": 1.25e-07,
    }
    result = _parse_model_entry("gpt-5-codex", entry)

    assert result is not None
    key, cost = result
    assert key == "gpt-5-codex"
    assert cost.input == 1.25
    assert cost.output == 10.0
    assert cost.cache_read == 0.125


def test_parse_model_entry_with_cache_creation_cost():
    entry = {
        "mode": "chat",
        "input_cost_per_token": 3e-06,
        "output_cost_per_token": 1.5e-05,
        "cache_read_input_token_cost": 3e-07,
        "cache_creation_input_token_cost": 3.75e-06,
    }

    result = _parse_model_entry("anthropic.claude-sonnet-4-5-20250929-v1:0", entry)

    assert result is not None
    _, cost = result
    assert cost.cache_write == 3.75


def test_parse_model_entry_without_cache_write():
    entry = {
        "mode": "chat",
        "input_cost_per_token": 3e-06,
        "output_cost_per_token": 1.5e-05,
    }

    result = _parse_model_entry("azure_ai/gpt-5.4", entry)

    assert result is not None
    _, cost = result
    assert cost.cache_write is None


def test_parse_model_entry_skips_non_chat():
    entry = {
        "mode": "image_generation",
        "output_cost_per_image": 0.06,
    }
    assert _parse_model_entry("dall-e-2", entry) is None


def test_parse_model_entry_skips_no_pricing():
    entry = {"mode": "chat"}
    assert _parse_model_entry("some-model", entry) is None


def test_parse_model_entry_with_tiered_pricing():
    entry = {
        "mode": "chat",
        "tiered_pricing": [
            {
                "cache_read_input_token_cost": 8e-08,
                "input_cost_per_token": 4e-07,
                "output_cost_per_token": 1.6e-06,
                "range": [0, 256000.0],
            },
            {
                "cache_read_input_token_cost": 2.4e-07,
                "input_cost_per_token": 1.2e-06,
                "output_cost_per_token": 4.8e-06,
                "range": [256000.0, 1000000.0],
            },
        ],
    }

    result = _parse_model_entry("dashscope/qwen3.7-plus", entry)

    assert result is not None
    key, cost = result
    assert key == "dashscope/qwen3.7-plus"
    # Flat fields default to the first tier (per-million)
    assert cost.input == 0.4
    assert cost.output == 1.6
    assert cost.cache_read == 0.08
    assert len(cost.tiers) == 2
    first, second = cost.tiers
    assert first.min_tokens == 0
    assert first.max_tokens == 256000
    assert first.input == 0.4
    assert first.output == 1.6
    assert first.cache_read == 0.08
    assert second.min_tokens == 256000
    assert second.max_tokens == 1000000
    assert second.input == 1.2
    assert second.output == 4.8
    assert second.cache_read == 0.24


def test_parse_model_entry_with_empty_tiered_pricing_still_skipped():
    entry = {"mode": "chat", "tiered_pricing": []}
    assert _parse_model_entry("some-model", entry) is None


def test_parse_model_entry_tier_falls_back_to_top_level_prices():
    entry = {
        "mode": "chat",
        "input_cost_per_token": 4e-07,
        "output_cost_per_token": 1.6e-06,
        "cache_read_input_token_cost": 8e-08,
        "tiered_pricing": [
            {
                "input_cost_per_token": 1.2e-06,
                "output_cost_per_token": 4.8e-06,
                "range": [256000.0, 1000000.0],
            }
        ],
    }

    result = _parse_model_entry("dashscope/some-model", entry)

    assert result is not None
    _, cost = result
    assert len(cost.tiers) == 1
    tier = cost.tiers[0]
    assert tier.input == 1.2
    assert tier.output == 4.8
    assert tier.cache_read == 0.08  # falls back to the entry's top-level value


def test_parse_model_entry_skips_malformed_tiers():
    entry = {
        "mode": "chat",
        "tiered_pricing": [
            {"input_cost_per_token": 4e-07, "range": [None, 1000]},
            {
                "input_cost_per_token": "bad",
                "output_cost_per_token": 1.6e-06,
                "range": [0, 256000],
            },
            {
                "input_cost_per_token": 1.2e-06,
                "output_cost_per_token": 4.8e-06,
                "range": [256000.0, 1000000.0],
            },
        ],
    }

    result = _parse_model_entry("dashscope/some-model", entry)

    assert result is not None
    _, cost = result
    assert len(cost.tiers) == 1
    assert cost.tiers[0].min_tokens == 256000
    assert cost.input == 1.2  # flat defaults to the first valid tier


# --- Full JSON parsing ---


def test_parse_litellm_json_extracts_chat_models():
    data = {
        "sample_spec": {"description": "schema"},
        "anthropic.claude-haiku-4-5-20251001-v1:0": {
            "mode": "chat",
            "input_cost_per_token": 1e-06,
            "output_cost_per_token": 5e-06,
            "cache_read_input_token_cost": 1e-07,
        },
        "dall-e-2": {
            "mode": "image_generation",
            "output_cost_per_pixel": 0.0,
        },
    }
    costs = _parse_litellm_json(data)

    # Date-stripped base name is kept, full key is deduplicated away
    assert "claude-haiku-4-5" in costs
    assert costs["claude-haiku-4-5"].input == 1.0
    # Image model should be skipped
    assert len(costs) >= 1


def test_parse_litellm_json_creates_base_name_alias():
    data = {
        "anthropic.claude-sonnet-4-5-20250929-v1:0": {
            "mode": "chat",
            "input_cost_per_token": 3e-06,
            "output_cost_per_token": 1.5e-05,
        },
    }
    costs = _parse_litellm_json(data)

    # Full key is deduplicated away, only base name kept
    assert "claude-sonnet-4-5-20250929-v1:0" not in costs
    assert "claude-sonnet-4-5" in costs
    assert costs["claude-sonnet-4-5"].input == 3.0


def test_parse_litellm_json_keys_are_lowercased():
    data = {
        "azure_ai/GPT-5.4": {
            "mode": "chat",
            "input_cost_per_token": 2.5e-06,
            "output_cost_per_token": 1.5e-05,
        },
    }
    costs = _parse_litellm_json(data)

    assert "gpt-5.4" in costs


# --- build_cost_maps integration ---


def test_remote_costs_fill_gaps(config_module):
    config = {
        "models": {
            "claude-sonnet-4-6": {
                "cost": {"input": 3.0, "output": 15.0, "cacheRead": 0.3}
            },
        },
        "providers": {},
    }
    remote = {
        "claude-sonnet-4-6": ModelCost(input=99.0, output=99.0, cache_read=99.0),
        "gpt-5.4": ModelCost(input=2.5, output=15.0, cache_read=0.25),
    }

    model_costs, _ = config_module.build_cost_maps(config, remote)

    # YAML wins for claude-sonnet-4-6
    assert model_costs["claude-sonnet-4-6"].input == 3.0
    # Remote fills gap for gpt-5.4
    assert model_costs["gpt-5.4"].input == 2.5


def test_remote_costs_do_not_override_yaml(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {},
    }
    remote = {
        "test-model": ModelCost(input=999.0, output=999.0, cache_read=999.0),
    }

    model_costs, _ = config_module.build_cost_maps(config, remote)

    assert model_costs["test-model"].input == 1.0


def test_remote_costs_none_uses_yaml_only(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {},
    }

    model_costs, _ = config_module.build_cost_maps(config, None)

    assert model_costs["test-model"].input == 1.0
    assert len(model_costs) == 1


def test_provider_override_takes_priority_over_remote(config_module):
    config = {
        "models": {},
        "providers": {
            "my-provider": {
                "base_url": "https://example.com",
                "models": {
                    "special-model": {
                        "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5},
                    },
                },
            },
        },
    }
    remote = {
        "special-model": ModelCost(input=1.0, output=2.0, cache_read=0.1),
    }

    model_costs, provider_costs = config_module.build_cost_maps(config, remote)

    # Provider override wins over remote
    assert provider_costs["my-provider"]["special-model"].input == 5.0
    # Remote also populates global (since no global YAML entry)
    assert model_costs["special-model"].input == 1.0


# --- resolve_all_costs integration ---


def test_resolve_all_costs_yaml_global(config_module):
    config = {
        "models": {
            "claude-sonnet-4-6": {
                "cost": {"input": 3.0, "output": 15.0, "cacheRead": 0.3}
            },
        },
        "providers": {},
    }

    resolved = config_module.resolve_all_costs(config)

    assert resolved.global_costs["claude-sonnet-4-6"].source == "yaml"
    assert resolved.global_costs["claude-sonnet-4-6"].cost.input == 3.0
    assert resolved.provider_costs == {}


def test_resolve_all_costs_provider_override_keeps_global(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {
            "my-provider": {
                "base_url": "https://example.com",
                "models": {
                    "test-model": {
                        "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                    },
                },
            },
        },
    }

    resolved = config_module.resolve_all_costs(config)

    assert resolved.global_costs["test-model"].cost.input == 1.0
    assert resolved.global_costs["test-model"].source == "yaml"
    assert resolved.provider_costs["my-provider"]["test-model"].cost.input == 5.0
    assert resolved.provider_costs["my-provider"]["test-model"].source == "yaml"


def test_resolve_all_costs_litellm_gap_fill(config_module):
    config = {
        "models": {"claude-sonnet-4-6": {}},
        "providers": {},
    }
    remote = {
        "claude-sonnet-4-6": ModelCost(input=3.0, output=15.0, cache_read=0.3),
    }

    resolved = config_module.resolve_all_costs(config, remote)

    assert resolved.global_costs["claude-sonnet-4-6"].source == "litellm"
    assert resolved.global_costs["claude-sonnet-4-6"].cost.input == 3.0


def test_resolve_all_costs_yaml_wins_over_litellm(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {},
    }
    remote = {
        "test-model": ModelCost(input=99.0, output=99.0, cache_read=99.0),
    }

    resolved = config_module.resolve_all_costs(config, remote)

    assert resolved.global_costs["test-model"].cost.input == 1.0
    assert resolved.global_costs["test-model"].source == "yaml"


def test_resolve_all_costs_partial_yaml_merges_with_litellm(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 9.0}},
        },
        "providers": {},
    }
    remote = {
        "test-model": ModelCost(
            input=1.0,
            output=2.0,
            cache_read=0.1,
            cache_write=0.25,
        ),
    }

    resolved = config_module.resolve_all_costs(config, remote)

    cost = resolved.global_costs["test-model"].cost
    assert resolved.global_costs["test-model"].source == "yaml"
    assert cost.input == 9.0
    assert cost.output == 2.0
    assert cost.cache_read == 0.1
    assert cost.cache_write == 0.25


def test_resolve_all_costs_partial_provider_yaml_merges_with_global(config_module):
    config = {
        "models": {
            "test-model": {
                "cost": {
                    "input": 1.0,
                    "output": 2.0,
                    "cacheRead": 0.1,
                    "cacheWrite": 0.25,
                }
            },
        },
        "providers": {
            "prov-a": {
                "base_url": "https://a.com",
                "models": {
                    "test-model": {
                        "cost": {"input": 9.0},
                    },
                },
            },
        },
    }

    resolved = config_module.resolve_all_costs(config)

    cost = resolved.provider_costs["prov-a"]["test-model"].cost
    assert resolved.provider_costs["prov-a"]["test-model"].source == "yaml"
    assert cost.input == 9.0
    assert cost.output == 2.0
    assert cost.cache_read == 0.1
    assert cost.cache_write == 0.25


def test_resolve_all_costs_both_scopes_coexist(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {
            "prov-a": {
                "base_url": "https://a.com",
                "models": {
                    "test-model": {
                        "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                    },
                },
            },
        },
    }

    resolved = config_module.resolve_all_costs(config)

    assert resolved.global_costs["test-model"].cost.input == 1.0
    assert resolved.provider_costs["prov-a"]["test-model"].cost.input == 5.0


def test_build_cost_maps_uses_resolved_behavior(config_module):
    config = {
        "models": {
            "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
        },
        "providers": {
            "prov-a": {
                "base_url": "https://a.com",
                "models": {
                    "test-model": {
                        "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                    },
                },
            },
        },
    }
    remote = {
        "remote-only": ModelCost(input=3.0, output=6.0, cache_read=0.3),
        "test-model": ModelCost(input=99.0, output=99.0, cache_read=99.0),
    }

    model_costs, provider_model_costs = config_module.build_cost_maps(config, remote)

    assert model_costs["test-model"].input == 1.0
    assert model_costs["remote-only"].input == 3.0
    assert provider_model_costs["prov-a"]["test-model"].input == 5.0


def test_pricing_endpoint_provider_display_overwrites_global_same_key(
    api_module, monkeypatch
):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
            },
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "models": {
                        "test-model": {
                            "cost": {
                                "input": 5.0,
                                "output": 10.0,
                                "cacheRead": 0.5,
                            }
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing")

    assert response.status_code == 200
    data = response.json()
    assert data["test-model"]["scope"] == "prov-a"
    assert data["test-model"]["source"] == "yaml"
    assert data["test-model"]["input"] == 5.0


def test_pricing_with_multiplier(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "fallback-model": {
                    "cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.25}
                },
            },
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "price_multiplier": 1.5,
                    "models": {
                        "override-model": {
                            "cost": {
                                "input": 5.0,
                                "output": 10.0,
                                "cacheRead": 0.5,
                                "cacheWrite": 6.0,
                            }
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing?provider=prov-a")

    assert response.status_code == 200
    data = response.json()
    assert data["override-model"]["input"] == 5.0
    assert data["override-model"]["output"] == 10.0
    assert data["override-model"]["cache_read"] == 0.5
    assert data["override-model"]["cache_write"] == 6.0
    assert data["override-model"]["scope"] == "prov-a"
    assert data["override-model"]["multiplier"] == 1.5
    assert data["override-model"]["effective_input"] == 7.5
    assert data["override-model"]["effective_output"] == 15.0
    assert data["override-model"]["effective_cache_read"] == 0.75
    assert data["override-model"]["effective_cache_write"] == 9.0


def test_pricing_without_provider_shows_all(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
            },
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "price_multiplier": 2.0,
                    "models": {
                        "test-model": {
                            "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                        },
                    },
                },
                "prov-b": {
                    "base_url": "https://b.com",
                    "models": {
                        "other-model": {
                            "cost": {"input": 7.0, "output": 14.0, "cacheRead": 0.7}
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {"remote-model": ModelCost(input=3.0, output=6.0, cache_read=0.3)},
    )

    response = TestClient(api_module.app).get("/pricing")

    assert response.status_code == 200
    data = response.json()
    assert data["test-model"]["scope"] == "prov-a"
    assert data["test-model"]["input"] == 5.0
    assert data["test-model"]["effective_input"] == 5.0
    assert data["test-model"]["multiplier"] == 1.0
    assert data["other-model"]["scope"] == "prov-b"
    assert data["remote-model"]["scope"] == "global"


def test_pricing_unknown_provider_defaults_multiplier_1(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "global-model": {
                    "cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}
                },
            },
            "providers": {},
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing?provider=missing")

    assert response.status_code == 200
    data = response.json()
    assert data["global-model"]["scope"] == "global"
    assert data["global-model"]["multiplier"] == 1.0
    assert data["global-model"]["effective_input"] == 1.0
    assert data["global-model"]["effective_output"] == 2.0
    assert data["global-model"]["effective_cache_read"] == 0.1


def test_pricing_two_providers_same_model_route_correctly(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {},
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "price_multiplier": 2.0,
                    "models": {
                        "shared-model": {
                            "cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}
                        },
                    },
                },
                "prov-b": {
                    "base_url": "https://b.com",
                    "price_multiplier": 3.0,
                    "models": {
                        "shared-model": {
                            "cost": {"input": 4.0, "output": 8.0, "cacheRead": 0.4}
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    prov_a = TestClient(api_module.app).get("/pricing?provider=prov-a").json()
    prov_b = TestClient(api_module.app).get("/pricing?provider=prov-b").json()

    assert prov_a["shared-model"]["scope"] == "prov-a"
    assert prov_a["shared-model"]["input"] == 1.0
    assert prov_a["shared-model"]["effective_input"] == 2.0
    assert prov_b["shared-model"]["scope"] == "prov-b"
    assert prov_b["shared-model"]["input"] == 4.0
    assert prov_b["shared-model"]["effective_input"] == 12.0


def test_pricing_provider_override_beats_global_and_fallback_gets_multiplier(
    api_module, monkeypatch
):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "shared-model": {
                    "cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}
                },
                "global-only": {
                    "cost": {"input": 3.0, "output": 6.0, "cacheRead": 0.3}
                },
            },
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "price_multiplier": 2.0,
                    "models": {
                        "shared-model": {
                            "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing?provider=prov-a")

    assert response.status_code == 200
    data = response.json()
    assert data["shared-model"]["scope"] == "prov-a"
    assert data["shared-model"]["input"] == 5.0
    assert data["shared-model"]["effective_input"] == 10.0
    assert data["global-only"]["scope"] == "global"
    assert data["global-only"]["input"] == 3.0
    assert data["global-only"]["multiplier"] == 2.0
    assert data["global-only"]["effective_input"] == 6.0


def test_single_model_pricing_contains_litellm_match(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {
            "openrouter/xiaomi/mimo-v2.5-pro": ModelCost(
                input=1.0, output=3.0, cache_read=0.2
            )
        },
    )

    response = TestClient(api_module.app).get("/pricing/mimo-v2.5-pro")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "openrouter/xiaomi/mimo-v2.5-pro"
    assert data["scope"] == "global"
    assert data["source"] == "litellm"
    assert data["input"] == 1.0
    assert data["output"] == 3.0
    assert data["cache_read"] == 0.2
    assert data["multiplier"] == 1.0
    assert data["tiers"] == []


def test_single_model_pricing_includes_tiers(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {
            "dashscope/qwen3.7-plus": ModelCost(
                input=0.4,
                output=1.6,
                cache_read=0.08,
                tiers=(
                    ModelTier(
                        min_tokens=0,
                        max_tokens=256000,
                        input=0.4,
                        output=1.6,
                        cache_read=0.08,
                    ),
                    ModelTier(
                        min_tokens=256000,
                        max_tokens=1000000,
                        input=1.2,
                        output=4.8,
                        cache_read=0.24,
                    ),
                ),
            )
        },
    )

    response = TestClient(api_module.app).get("/pricing/qwen3.7-plus")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["tiers"] == [
        {
            "min_tokens": 0,
            "max_tokens": 256000,
            "input": 0.4,
            "output": 1.6,
            "cache_read": 0.08,
        },
        {
            "min_tokens": 256000,
            "max_tokens": 1000000,
            "input": 1.2,
            "output": 4.8,
            "cache_read": 0.24,
        },
    ]


def test_single_model_pricing_unresolved_includes_empty_tiers(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/no-such-model")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is False
    assert data["tiers"] == []


def test_single_model_pricing_yaml_override_beats_litellm(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "test-model": {"cost": {"input": 2.0, "output": 4.0, "cacheRead": 0.2}},
            },
            "providers": {},
        }
    )
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {"test-model": ModelCost(input=9.0, output=9.0, cache_read=9.0)},
    )

    response = TestClient(api_module.app).get("/pricing/test-model")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "test-model"
    assert data["source"] == "yaml"
    assert data["input"] == 2.0
    assert data["output"] == 4.0


def test_single_model_pricing_provider_scope_and_multiplier(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "test-model": {"cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}},
            },
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "price_multiplier": 2.0,
                    "models": {
                        "test-model": {
                            "cost": {"input": 5.0, "output": 10.0, "cacheRead": 0.5}
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/test-model?provider=prov-a")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "test-model"
    assert data["scope"] == "prov-a"
    assert data["source"] == "yaml"
    assert data["input"] == 5.0
    assert data["multiplier"] == 2.0
    assert data["effective_input"] == 10.0
    assert data["effective_output"] == 20.0


def test_single_model_pricing_cheapest_contains_match(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {
            "openrouter/xiaomi/mimo-v2.5-pro": ModelCost(
                input=1.0, output=3.0, cache_read=0.2
            ),
            "gateway/xiaomi/mimo-v2.5-pro": ModelCost(
                input=0.5, output=1.0, cache_read=0.1
            ),
        },
    )

    response = TestClient(api_module.app).get("/pricing/mimo-v2.5-pro")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "gateway/xiaomi/mimo-v2.5-pro"
    assert data["input"] == 0.5


def test_single_model_pricing_slashed_model_exact_yaml(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {
                "z-ai/glm-5.1-20260406": {
                    "cost": {"input": 0.98, "output": 3.08, "cacheRead": 0.182}
                },
            },
            "providers": {},
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/z-ai/glm-5.1-20260406")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "z-ai/glm-5.1-20260406"
    assert data["source"] == "yaml"
    assert data["input"] == 0.98


def test_single_model_pricing_unresolved(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/unknown-model")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is False
    assert data["model"] == "unknown-model"
    assert data["input"] == 0.0
    assert data["output"] == 0.0


def test_single_model_pricing_provider_contains_match(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update(
        {
            "models": {},
            "providers": {
                "prov-a": {
                    "base_url": "https://a.com",
                    "models": {
                        "gateway/mimo-v2.5-pro": {
                            "cost": {"input": 2.0, "output": 4.0, "cacheRead": 0.2}
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/mimo-v2.5-pro?provider=prov-a")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "gateway/mimo-v2.5-pro"
    assert data["scope"] == "prov-a"
    assert data["source"] == "yaml"
    assert data["input"] == 2.0


def test_single_model_pricing_case_insensitive(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr(
        "config.pricing.get_remote_pricing",
        lambda: {
            "openrouter/xiaomi/mimo-v2.5-pro": ModelCost(
                input=1.0, output=3.0, cache_read=0.2
            )
        },
    )

    response = TestClient(api_module.app).get("/pricing/Mimo-V2.5-Pro")

    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["model"] == "openrouter/xiaomi/mimo-v2.5-pro"
    assert data["input"] == 1.0


def test_single_model_pricing_rejects_empty_model(api_module, monkeypatch):
    api_module.CONFIG.clear()
    api_module.CONFIG.update({"models": {}, "providers": {}})
    monkeypatch.setattr("config.pricing.get_remote_pricing", lambda: {})

    response = TestClient(api_module.app).get("/pricing/")

    assert response.status_code == 422


def test_patch_config_applies_patches_and_refreshes_runtime(
    api_module, isolated_home, monkeypatch
):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    config_path.write_text(
        """# tracker config
server:
  host: 127.0.0.1
  port: 4000
db:
  path: ~/.llm-tracker/usage.db
models:
  test-model:
    cost:
      input: 1.0
      output: 2.0
      cacheRead: 0.1
providers: {}
""",
        encoding="utf-8",
    )
    api_module.CONFIG_PATH = str(config_path)
    refreshed_paths = []
    monkeypatch.setattr(
        api_module,
        "refresh_runtime_config",
        lambda path: refreshed_paths.append(path),
    )

    response = TestClient(api_module.app).patch(
        "/config",
        json={
            "patches": [
                {
                    "path": ["models", "test-model", "cost", "input"],
                    "op": "set",
                    "value": 3.5,
                },
                {
                    "path": ["models", "test-model", "cost", "cacheRead"],
                    "op": "delete",
                    "value": None,
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    content = config_path.read_text(encoding="utf-8")
    assert "# tracker config" in content
    assert "input: 3.5" in content
    assert "cacheRead" not in content
    assert refreshed_paths == [str(config_path)]


def test_patch_config_rejects_non_numeric_set_value(api_module, isolated_home):
    response = TestClient(api_module.app).patch(
        "/config",
        json={
            "patches": [
                {
                    "path": ["models", "test-model", "cost", "input"],
                    "op": "set",
                    "value": "not-a-number",
                },
            ]
        },
    )

    assert response.status_code == 422


def test_patch_config_rejects_numeric_string_set_value(api_module, isolated_home):
    response = TestClient(api_module.app).patch(
        "/config",
        json={
            "patches": [
                {
                    "path": ["models", "test-model", "cost", "input"],
                    "op": "set",
                    "value": "1.2",
                },
            ]
        },
    )

    assert response.status_code == 422


def test_patch_config_rejects_null_set_value_without_persisting(
    api_module, isolated_home
):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    original_content = config_path.read_text(encoding="utf-8")

    response = TestClient(api_module.app).patch(
        "/config",
        json={
            "patches": [
                {
                    "path": ["models", "test-model", "cost", "input"],
                    "op": "set",
                    "value": None,
                },
            ]
        },
    )

    assert response.status_code == 422
    assert config_path.read_text(encoding="utf-8") == original_content


def test_patch_config_rejects_missing_set_value_without_persisting(
    api_module, isolated_home
):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    original_content = config_path.read_text(encoding="utf-8")

    response = TestClient(api_module.app).patch(
        "/config",
        json={
            "patches": [
                {
                    "path": ["models", "test-model", "cost", "input"],
                    "op": "set",
                },
            ]
        },
    )

    assert response.status_code == 422
    assert config_path.read_text(encoding="utf-8") == original_content


# --- Claude 3.x alias ---


def test_claude_3x_alias_sonnet():
    assert _claude_3x_alias("claude-3-7-sonnet") == "claude-sonnet-3-7"


def test_claude_3x_alias_opus():
    assert _claude_3x_alias("claude-3-opus") == "claude-opus-3"


def test_claude_3x_alias_haiku():
    assert _claude_3x_alias("claude-3-5-haiku") == "claude-haiku-3-5"


def test_claude_3x_alias_no_match():
    assert _claude_3x_alias("claude-sonnet-4-6") is None


def test_parse_litellm_json_creates_claude_3x_alias():
    data = {
        "claude-3-7-sonnet": {
            "mode": "chat",
            "input_cost_per_token": 3e-06,
            "output_cost_per_token": 1.5e-05,
        },
    }
    costs = _parse_litellm_json(data)

    assert "claude-3-7-sonnet" in costs
    assert "claude-sonnet-3-7" in costs
    assert costs["claude-3-7-sonnet"] == costs["claude-sonnet-3-7"]


def test_parse_litellm_json_claude_3x_alias_with_date():
    data = {
        "claude-3-7-sonnet-20250219": {
            "mode": "chat",
            "input_cost_per_token": 3e-06,
            "output_cost_per_token": 1.5e-05,
        },
    }
    costs = _parse_litellm_json(data)

    # Full key with date is deduplicated away
    assert "claude-3-7-sonnet-20250219" not in costs
    # Date-stripped base name
    assert "claude-3-7-sonnet" in costs
    # Claude 3.x alias
    assert "claude-sonnet-3-7" in costs


# --- Cache TTL ---


def test_fetch_remote_pricing_skips_network_when_cache_fresh(tmp_path, monkeypatch):
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text(
        json.dumps({"gpt-fresh": {"input_cost_per_token": 1e-06, "mode": "chat"}})
    )
    monkeypatch.setattr(pricing_module, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(pricing_module, "_remote_costs", None)

    def _fail_if_called():
        raise AssertionError("should not hit the network when cache is fresh")

    monkeypatch.setattr(pricing_module, "_fetch_litellm_json", _fail_if_called)

    costs = fetch_remote_pricing()

    assert "gpt-fresh" in costs


def test_fetch_remote_pricing_refetches_when_cache_stale(tmp_path, monkeypatch):
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text(
        json.dumps({"gpt-old": {"input_cost_per_token": 1e-06, "mode": "chat"}})
    )
    stale_mtime = time.time() - pricing_module.CACHE_TTL_SECONDS - 1
    os.utime(cache_path, (stale_mtime, stale_mtime))

    monkeypatch.setattr(pricing_module, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(pricing_module, "_remote_costs", None)
    monkeypatch.setattr(
        pricing_module,
        "_fetch_litellm_json",
        lambda: {"gpt-new": {"input_cost_per_token": 2e-06, "mode": "chat"}},
    )

    costs = fetch_remote_pricing()

    assert "gpt-new" in costs
    assert "gpt-old" not in costs
    # Cache file on disk was refreshed with the newly fetched data.
    assert "gpt-new" in json.loads(cache_path.read_text())


def test_fetch_remote_pricing_refetches_when_fresh_cache_is_corrupt(
    tmp_path, monkeypatch
):
    """A fresh mtime with unparseable content (truncated/corrupt write)
    must not block a real fetch for a full CACHE_TTL_SECONDS."""
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text("{not valid json")  # fresh mtime, but garbage content

    monkeypatch.setattr(pricing_module, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(pricing_module, "_remote_costs", None)
    monkeypatch.setattr(
        pricing_module,
        "_fetch_litellm_json",
        lambda: {"gpt-recovered": {"input_cost_per_token": 1e-06, "mode": "chat"}},
    )

    costs = fetch_remote_pricing()

    assert "gpt-recovered" in costs


# --- IPv4-only fetch (scoped, not a global socket.getaddrinfo patch) ---


def test_create_ipv4_connection_requests_af_inet_only(monkeypatch):
    seen_family = {}

    class _FakeSocket:
        def __init__(self):
            self.connected_to = None

        def settimeout(self, _):
            pass

        def connect(self, sockaddr):
            self.connected_to = sockaddr

        def close(self):
            pass

    def _fake_getaddrinfo(host, port, family, socktype):
        seen_family["family"] = family
        return [(family, socktype, 0, "", (host, port))]

    fake_sock = _FakeSocket()
    monkeypatch.setattr(pricing_module.socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(pricing_module.socket, "socket", lambda *a, **k: fake_sock)

    result = pricing_module._create_ipv4_connection(("example.com", 443))

    assert seen_family["family"] == pricing_module.socket.AF_INET
    assert result is fake_sock
    assert fake_sock.connected_to == ("example.com", 443)


def test_create_ipv4_connection_raises_when_all_candidates_fail(monkeypatch):
    class _FakeSocket:
        def settimeout(self, _):
            pass

        def connect(self, sockaddr):
            raise OSError("connection refused")

        def close(self):
            pass

    monkeypatch.setattr(
        pricing_module.socket,
        "getaddrinfo",
        lambda host, port, family, socktype: [(family, socktype, 0, "", (host, port))],
    )
    monkeypatch.setattr(pricing_module.socket, "socket", lambda *a, **k: _FakeSocket())

    try:
        pricing_module._create_ipv4_connection(("example.com", 443))
        raise AssertionError("expected OSError")
    except OSError as exc:
        assert "connection refused" in str(exc)


def test_fetch_litellm_json_does_not_mutate_global_getaddrinfo(monkeypatch):
    """Regression guard for the original bug: this must not monkeypatch
    socket.getaddrinfo globally, since the same process also resolves DNS
    for concurrent, unrelated live proxy traffic."""
    original_getaddrinfo = pricing_module.socket.getaddrinfo

    class _RaisingOpener:
        def open(self, *a, **k):
            raise urllib.error.URLError("network unavailable in test")

    monkeypatch.setattr(
        pricing_module.urllib.request, "build_opener", lambda *a, **k: _RaisingOpener()
    )

    result = pricing_module._fetch_litellm_json()

    assert result is None
    assert pricing_module.socket.getaddrinfo is original_getaddrinfo
