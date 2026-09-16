"""Pricing domain: models, LiteLLM fetching, runtime maps, cost calculation,
and per-day price snapshots.

Import from the specific submodule (e.g. ``from src.pricing.snapshots import
enrich_rows``); the package ``__init__`` deliberately imports nothing so
``config.app`` can import ``src.pricing.maps`` without triggering a cycle.
"""
