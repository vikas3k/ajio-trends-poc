"""Gemini call helpers shared by the agents.

Two modes:
  - grounded_call:   Gemini + Google Search grounding (live market/social signal),
                     returns free text. (Grounding can't be combined with a JSON
                     response schema, so this is the "research" mode.)
  - structured_call: Gemini with a Pydantic response schema, returns parsed objects.

Both retry transient network errors and log a Langfuse generation when tracing
is configured.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

API_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "120"))  # seconds per call

from google import genai
from google.genai import types

from . import prompts as _prompts
from .observability import get_client

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

_genai_client = None


def _client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client()  # Vertex AI via env vars
    return _genai_client


def _usage(resp) -> dict:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return {}
    return {
        "input": getattr(u, "prompt_token_count", None),
        "output": getattr(u, "candidates_token_count", None),
        "total": getattr(u, "total_token_count", None),
    }


def _generate(prompt: str, config: types.GenerateContentConfig, name: str,
              retries: int = 4) -> Any:
    """Call Gemini with retry/backoff; trace as a Langfuse generation if enabled."""
    lf = get_client()
    gen_cm = (
        lf.start_as_current_generation(
            name=name, model=DEFAULT_MODEL, input=prompt,
            metadata={"prompt_version": _prompts.version()},
        )
        if lf is not None else None
    )
    if gen_cm is not None:
        gen_cm.__enter__()
    try:
        last = None
        for attempt in range(1, retries + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        _client().models.generate_content,
                        model=DEFAULT_MODEL, contents=prompt, config=config,
                    )
                    try:
                        resp = future.result(timeout=API_TIMEOUT)
                    except FuturesTimeoutError:
                        raise TimeoutError(f"Vertex call timed out after {API_TIMEOUT}s")
                if lf is not None:
                    try:
                        lf.update_current_generation(
                            output=getattr(resp, "text", None),
                            usage_details=_usage(resp),
                            metadata={"prompt_version": _prompts.version()},
                        )
                    except Exception:
                        pass
                return resp
            except Exception as e:
                last = e
                if attempt == retries:
                    raise
                wait = 2 ** attempt
                print(f"  [{name}] retry {attempt}/{retries - 1} after {e}; waiting {wait}s")
                time.sleep(wait)
        raise last  # pragma: no cover
    finally:
        if gen_cm is not None:
            gen_cm.__exit__(None, None, None)


def grounded_call(prompt: str, system: str | None = None,
                  name: str = "grounded_research", temperature: float = 0.4) -> str:
    """Gemini + Google Search grounding. Returns free text (no JSON schema)."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=temperature,
    )
    resp = _generate(prompt, config, name)
    return getattr(resp, "text", "") or ""


def structured_call(prompt: str, schema, system: str | None = None,
                    name: str = "structured", temperature: float = 0.5):
    """Gemini with a Pydantic response schema. Returns resp.parsed."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
    )
    resp = _generate(prompt, config, name)
    return resp.parsed
