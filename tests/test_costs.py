from decimal import Decimal


def _sync_segment_index(config_module):
    config_module.MODEL_SEGMENT_COSTS.clear()
    config_module.MODEL_SEGMENT_COSTS.update(
        config_module.build_segment_index(config_module.MODEL_COSTS)
    )
    config_module.PROVIDER_MODEL_SEGMENT_COSTS.clear()
    config_module.PROVIDER_MODEL_SEGMENT_COSTS.update(
        {
            provider: config_module.build_segment_index(costs)
            for provider, costs in config_module.PROVIDER_MODEL_COSTS.items()
        }
    )


def test_build_segment_index_keeps_cheapest_per_segment(config_module):
    index = config_module.build_segment_index(
        {
            "openrouter/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=1.0, output=3.0, cache_read=0.2
            ),
            "gateway/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=0.5, output=1.0, cache_read=0.1
            ),
        }
    )

    assert index["mimo-v2.5-pro"] == (
        "gateway/xiaomi/mimo-v2.5-pro",
        config_module.ModelCost(input=0.5, output=1.0, cache_read=0.1),
    )


def test_resolve_model_cost_prefers_provider_override(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "alpha-1": config_module.ModelCost(
                input=1.0,
                output=2.0,
                cache_read=0.1,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.update(
        {
            "alpha": {
                "alpha-1": config_module.ModelCost(
                    input=3.0,
                    output=4.0,
                    cache_read=0.3,
                )
            }
        }
    )

    assert costs_module.resolve_model_cost(
        "alpha", "alpha-1"
    ) == config_module.ModelCost(
        input=3.0,
        output=4.0,
        cache_read=0.3,
    )


def test_resolve_model_cost_falls_back_to_global(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "alpha-1": config_module.ModelCost(
                input=1.5,
                output=2.5,
                cache_read=0.15,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()

    assert costs_module.resolve_model_cost(
        "alpha", "alpha-1"
    ) == config_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )


def test_resolve_model_cost_matches_model_names_case_insensitively(
    costs_module, config_module
):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "minimax-m2.7": config_module.ModelCost(
                input=1.5,
                output=2.5,
                cache_read=0.15,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()

    assert costs_module.resolve_model_cost(
        "alpha", "MiniMax-M2.7"
    ) == config_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )


def test_resolve_model_cost_matches_containing_model_name(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "openrouter/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=1.0,
                output=3.0,
                cache_read=0.2,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()

    _sync_segment_index(config_module)

    assert costs_module.resolve_model_cost(
        "openrouter", "mimo-v2.5-pro"
    ) == config_module.ModelCost(input=1.0, output=3.0, cache_read=0.2)


def test_resolve_model_cost_uses_cheapest_containing_match(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "openrouter/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=1.0,
                output=3.0,
                cache_read=0.2,
            ),
            "gateway/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=0.5,
                output=1.0,
                cache_read=0.1,
            ),
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()

    _sync_segment_index(config_module)

    assert costs_module.resolve_model_cost(
        "openrouter", "mimo-v2.5-pro"
    ) == config_module.ModelCost(input=0.5, output=1.0, cache_read=0.1)


def test_resolve_model_cost_does_not_match_model_variant(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "openrouter/openai/gpt-5-mini": config_module.ModelCost(
                input=0.25,
                output=2.0,
                cache_read=0.025,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()

    _sync_segment_index(config_module)

    assert costs_module.resolve_model_cost("openrouter", "gpt-5") is None


def test_resolve_model_cost_prefers_provider_containing_match(
    costs_module, config_module
):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "openrouter/xiaomi/mimo-v2.5-pro": config_module.ModelCost(
                input=0.1,
                output=0.1,
                cache_read=0.1,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.update(
        {
            "x": {
                "gateway/mimo-v2.5-pro": config_module.ModelCost(
                    input=2.0,
                    output=3.0,
                    cache_read=0.2,
                )
            }
        }
    )

    _sync_segment_index(config_module)

    assert costs_module.resolve_model_cost(
        "x", "mimo-v2.5-pro"
    ) == config_module.ModelCost(input=2.0, output=3.0, cache_read=0.2)


def test_resolve_model_cost_global_exact_beats_provider_containing(
    costs_module, config_module
):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(
        {
            "mimo-v2.5-pro": config_module.ModelCost(
                input=1.0,
                output=2.0,
                cache_read=0.1,
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.update(
        {
            "x": {
                "gateway/mimo-v2.5-pro": config_module.ModelCost(
                    input=5.0,
                    output=6.0,
                    cache_read=0.5,
                )
            }
        }
    )

    _sync_segment_index(config_module)

    assert costs_module.resolve_model_cost(
        "x", "mimo-v2.5-pro"
    ) == config_module.ModelCost(input=1.0, output=2.0, cache_read=0.1)


def test_resolve_model_cost_returns_none_for_unknown_model(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.clear()

    assert costs_module.resolve_model_cost("missing", "missing-model") is None


def test_calculate_costs_computes_provider_model_costs(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.PROVIDER_MAP.clear()
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MAP.update(
        {
            "alpha": config_module.ProviderConfig(
                name="alpha", base_url="https://alpha.example", price_multiplier=1.0
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.update(
        {
            "alpha": {
                "alpha-1": config_module.ModelCost(
                    input=2.0,
                    output=6.0,
                    cache_read=0.5,
                )
            }
        }
    )

    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        provider="alpha",
        model="alpha-1",
    )

    assert result == {
        "input_cost_usd": Decimal("0.0017"),
        "output_cost_usd": Decimal("0.003"),
        "total_cost_usd": Decimal("0.0047"),
    }


def test_calculate_costs_returns_zero_for_missing_pricing(costs_module, config_module):
    config_module.PROVIDER_MAP.clear()
    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        provider="missing",
        model="missing-model",
    )

    assert result == {
        "input_cost_usd": Decimal("0"),
        "output_cost_usd": Decimal("0"),
        "total_cost_usd": Decimal("0"),
    }


def test_calculate_costs_clamps_negative_uncached_input(costs_module, config_module):
    result = costs_module.calculate_costs(
        prompt_tokens=50,
        completion_tokens=0,
        cached_tokens=100,
        model_cost=config_module.ModelCost(input=2.0, output=4.0, cache_read=0.5),
    )

    assert result == {
        "input_cost_usd": Decimal("0.00005"),
        "output_cost_usd": Decimal("0"),
        "total_cost_usd": Decimal("0.00005"),
    }


def test_calculate_costs_includes_cache_write_cost(costs_module, config_module):
    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        cache_creation_tokens=100,
        model_cost=config_module.ModelCost(
            input=2.0, output=4.0, cache_read=0.5, cache_write=3.0
        ),
    )

    # input: (1000-200)*2.0/1e6=0.0016, cache_read: 200*0.5/1e6=0.0001,
    # cache_write: 100*3.0/1e6=0.0003, output: 500*4.0/1e6=0.002
    assert result == {
        "input_cost_usd": Decimal("0.0020"),
        "output_cost_usd": Decimal("0.002"),
        "total_cost_usd": Decimal("0.0040"),
    }


def test_calculate_costs_treats_missing_cache_write_price_as_zero(
    costs_module, config_module
):
    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=0,
        cached_tokens=0,
        cache_creation_tokens=500,
        model_cost=config_module.ModelCost(input=2.0, output=4.0, cache_read=0.5),
    )

    assert result == {
        "input_cost_usd": Decimal("0.002"),
        "output_cost_usd": Decimal("0"),
        "total_cost_usd": Decimal("0.002"),
    }


def test_calculate_costs_applies_provider_price_multiplier(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MAP.clear()
    config_module.PROVIDER_MAP.update(
        {
            "alpha": config_module.ProviderConfig(
                name="alpha", base_url="https://alpha.example", price_multiplier=1.5
            )
        }
    )
    config_module.PROVIDER_MODEL_COSTS.update(
        {
            "alpha": {
                "alpha-1": config_module.ModelCost(
                    input=2.0,
                    output=6.0,
                    cache_read=0.5,
                )
            }
        }
    )

    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        provider="alpha",
        model="alpha-1",
    )

    assert result == {
        "input_cost_usd": Decimal("0.00255"),
        "output_cost_usd": Decimal("0.0045"),
        "total_cost_usd": Decimal("0.00705"),
    }


def _tiered_cost(config_module):
    return config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        tiers=(
            config_module.ModelTier(
                min_tokens=0,
                max_tokens=256000,
                input=0.4,
                output=1.6,
                cache_read=0.08,
            ),
            config_module.ModelTier(
                min_tokens=256000,
                max_tokens=1000000,
                input=1.2,
                output=4.8,
                cache_read=0.24,
            ),
        ),
    )


def test_calculate_costs_uses_first_tier_below_range(costs_module, config_module):
    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        model_cost=_tiered_cost(config_module),
    )

    # input: 800*0.4/1e6, cache_read: 200*0.08/1e6, output: 500*1.6/1e6
    assert result == {
        "input_cost_usd": Decimal("0.000336"),
        "output_cost_usd": Decimal("0.0008"),
        "total_cost_usd": Decimal("0.001136"),
    }


def test_calculate_costs_uses_second_tier_for_long_context(costs_module, config_module):
    result = costs_module.calculate_costs(
        prompt_tokens=300000,
        completion_tokens=500,
        cached_tokens=100000,
        model_cost=_tiered_cost(config_module),
    )

    # input: 200000*1.2/1e6, cache_read: 100000*0.24/1e6, output: 500*4.8/1e6
    assert result == {
        "input_cost_usd": Decimal("0.264"),
        "output_cost_usd": Decimal("0.0024"),
        "total_cost_usd": Decimal("0.2664"),
    }


def test_calculate_costs_falls_back_to_last_tier_above_range(
    costs_module, config_module
):
    result = costs_module.calculate_costs(
        prompt_tokens=2000000,
        completion_tokens=0,
        cached_tokens=0,
        model_cost=_tiered_cost(config_module),
    )

    assert result == {
        "input_cost_usd": Decimal("2.4"),
        "output_cost_usd": Decimal("0"),
        "total_cost_usd": Decimal("2.4"),
    }


def test_calculate_costs_tier_selection_counts_cache_creation_tokens(
    costs_module, config_module
):
    result = costs_module.calculate_costs(
        prompt_tokens=256000,
        completion_tokens=0,
        cached_tokens=0,
        cache_creation_tokens=100,
        model_cost=_tiered_cost(config_module),
    )

    # 256100 total input tokens crosses into the second tier (input price 1.2);
    # uncached input is 256000, cache-created tokens are charged at cache_write
    assert result["input_cost_usd"] == Decimal("0.3072")


def test_calculate_costs_tier_boundary_uses_next_tier_at_exact_max(
    costs_module, config_module
):
    result = costs_module.calculate_costs(
        prompt_tokens=256000,
        completion_tokens=0,
        cached_tokens=0,
        model_cost=_tiered_cost(config_module),
    )

    # tokens == first tier's max_tokens: half-open range puts it in tier 2
    assert result["input_cost_usd"] == Decimal("0.3072")


def test_calculate_costs_flat_cache_write_with_tiers(costs_module, config_module):
    cost = config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        cache_write=3.0,
        tiers=(
            config_module.ModelTier(
                min_tokens=0, max_tokens=256000, input=0.4, output=1.6, cache_read=0.08
            ),
        ),
    )
    result = costs_module.calculate_costs(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        cache_creation_tokens=100,
        model_cost=cost,
    )

    # input: 800*0.4/1e6, cache_read: 200*0.08/1e6, cache_write: 100*3.0/1e6,
    # output: 500*1.6/1e6 — cache_write stays flat, tier rates for the rest
    assert result == {
        "input_cost_usd": Decimal("0.000636"),
        "output_cost_usd": Decimal("0.0008"),
        "total_cost_usd": Decimal("0.001436"),
    }


def test_calculate_costs_uses_per_tier_cache_write_price(costs_module, config_module):
    cost = config_module.ModelCost(
        input=0.4,
        output=1.6,
        cache_read=0.08,
        cache_write=3.0,
        tiers=(
            config_module.ModelTier(
                min_tokens=0,
                max_tokens=256000,
                input=0.4,
                output=1.6,
                cache_read=0.08,
                cache_write=3.0,
            ),
            config_module.ModelTier(
                min_tokens=256000,
                max_tokens=1000000,
                input=1.2,
                output=4.8,
                cache_read=0.24,
                cache_write=7.5,
            ),
        ),
    )
    result = costs_module.calculate_costs(
        prompt_tokens=300000,
        completion_tokens=0,
        cached_tokens=0,
        cache_creation_tokens=100,
        model_cost=cost,
    )

    # 300000 total input tokens is in the second tier: cache_write should use
    # that tier's 7.5 rate, not the flat 3.0 rate.
    assert result["input_cost_usd"] == Decimal("0.36075")


def test_calculate_costs_tiered_pricing_applies_provider_multiplier(
    costs_module, config_module
):
    config_module.PROVIDER_MAP.clear()
    config_module.PROVIDER_MAP.update(
        {
            "alpha": config_module.ProviderConfig(
                name="alpha", base_url="https://alpha.example", price_multiplier=2.0
            )
        }
    )

    result = costs_module.calculate_costs(
        prompt_tokens=300000,
        completion_tokens=500,
        cached_tokens=100000,
        provider="alpha",
        model_cost=_tiered_cost(config_module),
    )

    assert result == {
        "input_cost_usd": Decimal("0.528"),
        "output_cost_usd": Decimal("0.0048"),
        "total_cost_usd": Decimal("0.5328"),
    }
