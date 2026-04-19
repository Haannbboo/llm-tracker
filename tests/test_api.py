def test_build_usage_query_without_filters(api_module):
    query, params = api_module.build_usage_query(limit=25)

    assert query == "SELECT * FROM usage ORDER BY ts DESC LIMIT ? OFFSET ?"
    assert params == (25, 0)


def test_build_usage_query_with_provider_filter(api_module):
    query, params = api_module.build_usage_query(limit=10, provider="vectorengine")

    assert (
        query
        == "SELECT * FROM usage WHERE provider = ? ORDER BY ts DESC LIMIT ? OFFSET ?"
    )
    assert params == ("vectorengine", 10, 0)


def test_build_usage_query_with_model_filter(api_module):
    query, params = api_module.build_usage_query(limit=10, model="gpt-5.4-medium")

    assert (
        query == "SELECT * FROM usage WHERE model = ? ORDER BY ts DESC LIMIT ? OFFSET ?"
    )
    assert params == ("gpt-5.4-medium", 10, 0)


def test_build_usage_query_with_provider_and_model_filters(api_module):
    query, params = api_module.build_usage_query(
        limit=50,
        provider="vectorengine",
        model="gpt-5.4-medium",
    )

    assert (
        query
        == "SELECT * FROM usage WHERE provider = ? AND model = ? ORDER BY ts DESC LIMIT ? OFFSET ?"
    )
    assert params == ("vectorengine", "gpt-5.4-medium", 50, 0)
