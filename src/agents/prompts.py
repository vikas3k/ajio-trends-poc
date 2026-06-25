"""Loader for the externalised prompts in `prompts.yaml` (project root).

Edit prompts in prompts.yaml, not in the agent code. Shared blocks referenced as
`<<curated_brief>>` / `<<naming_principles>>` are inlined here at load time;
`{placeholders}` are filled by the agents at call time via `fmt()`.

    from . import prompts
    prompts.get("agent1.system")
    prompts.fmt("agent1.select_columns", preview=preview)
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import yaml

# project root = two levels up from src/agents/prompts.py
_DEFAULT = Path(__file__).resolve().parents[2] / "prompts.yaml"
PROMPTS_PATH = Path(os.getenv("PROMPTS_FILE", _DEFAULT))


@functools.lru_cache(maxsize=1)
def _data() -> dict:
    raw = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8"))
    shared = {k: str(v).rstrip("\n") for k, v in (raw.get("shared") or {}).items()}

    def inline(s):
        if not isinstance(s, str):
            return s
        for k, v in shared.items():
            s = s.replace(f"<<{k}>>", v)
        return s.rstrip("\n")

    out = {}
    for section, vals in raw.items():
        if isinstance(vals, dict):
            out[section] = {k: inline(v) for k, v in vals.items()}
        else:
            out[section] = vals
    return out


def version() -> str:
    """Return the current prompt version string (top-level 'version:' in prompts.yaml)."""
    return str(_data().get("version", "unknown"))


def get(path: str) -> str:
    """Return a resolved prompt by 'section.key' (e.g. 'agent2.attr_system')."""
    section, key = path.split(".", 1)
    return _data()[section][key]


def fmt(path: str, **kwargs) -> str:
    """Return a prompt with its {placeholders} filled."""
    return get(path).format(**kwargs)
