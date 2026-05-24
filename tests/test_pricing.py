from __future__ import annotations

from fastapi.testclient import TestClient

from config.app import ModelCost
from config.pricing import (
    _claude_3x_alias,
    _is_chat_model,
    _parse_litellm_json,
    _parse_model_entry,
    _strip_provider_prefix,
    _strip_version_suffix,
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
