"""Langfuse wiring for the agent graph.

Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from the
environment. If the keys aren't set, tracing degrades to a no-op so the graph
still runs locally without Langfuse.
"""
from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def langfuse_enabled() -> bool:
    # Accept LANGFUSE_BASE_URL as an alias for the SDK's LANGFUSE_HOST.
    if not os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


@lru_cache(maxsize=1)
def get_client():
    """Return a configured Langfuse client, or None if keys are absent."""
    if not langfuse_enabled():
        return None
    try:
        from langfuse import get_client as _get
        client = _get()
        return client
    except Exception as e:  # never let tracing break the run
        print(f"[langfuse] disabled ({e})")
        return None


def flush() -> None:
    client = get_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
