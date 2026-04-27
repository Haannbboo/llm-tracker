from decimal import Decimal


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


def test_resolve_model_cost_returns_none_for_unknown_model(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.clear()

    assert costs_module.resolve_model_cost("missing", "missing-model") is None


def test_calculate_costs_computes_provider_model_costs(costs_module, config_module):
    config_module.MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.clear()
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


def test_calculate_costs_returns_zero_for_missing_pricing(costs_module):
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
