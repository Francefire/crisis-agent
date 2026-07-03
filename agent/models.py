"""
Model registry — score candidate models per (provider, tier) and pick the
STRONGEST that is actually AVAILABLE on the provider (live model list, cached),
honouring an env-preferred model first.

Why: hard-coding one model per tier breaks when it's unavailable or when a newer/
better one appears (Qwen vs Llama on Groq, Mistral's own line, …). Instead each
tier lists scored candidates (declared in `providers.PROVIDERS`); `resolve()`
returns them best-first, filtered to what the key can really see, so
`llm._leaf_models` builds a chain that tries the best model, then the next, then
the next key/provider — the rotation mixin walks it.

The candidate LISTS and their scores live in `providers.py` (the single provider
registry); this module owns only the *policy*: live availability caching, the
env-preferred override, and best-first ordering. Override any cell with env
LLM_<PROVIDER>_<TIER> (e.g. LLM_GROQ_BIG=…): that model is tried FIRST, then the
scored list as backup.
"""
from __future__ import annotations

import os
import json
import time

from dotenv import load_dotenv

import providers
from runlog import get_logger

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
load_dotenv(os.path.join(ROOT, ".env"))
_LOG = get_logger()

CACHE = os.path.join(HERE, "out", "model_cache.json")
CACHE_TTL = 24 * 3600      # refetch a provider's model list at most once a day


# ------------------------------------------------------- live availability
def _fetch_ids(provider: str) -> list | None:
    """The model ids the key can actually see (None = couldn't fetch → assume all).
    The per-provider list call lives in the registry (`providers.spec[...]['list_ids']`)."""
    key = providers.first_key(provider)
    list_ids = providers.spec(provider).get("list_ids")
    if not key or list_ids is None:            # no key, or provider has no cheap list
        return None
    try:
        return list_ids(key)
    except Exception as e:                       # network/auth/SDK issue → be lenient
        _LOG.warning("model-list fetch failed for %s: %s", provider, str(e)[:80])
        return None


def _load_cache() -> dict:
    try:
        with open(CACHE) as f:
            return json.load(f)
    except Exception:
        return {}


def available_ids(provider: str) -> set | None:
    """Cached set of available model ids for `provider` (None = unknown → allow all)."""
    cache = _load_cache()
    ent = cache.get(provider)
    if ent and (time.time() - ent["ts"]) < CACHE_TTL:
        return set(ent["ids"]) if ent["ids"] is not None else None
    ids = _fetch_ids(provider)
    cache[provider] = {"ids": ids, "ts": time.time()}
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass
    return set(ids) if ids is not None else None


# ------------------------------------------------------------- resolution
_logged: set = set()


def _preferred(provider: str, tier: str) -> str | None:
    return os.environ.get(f"LLM_{provider.upper()}_{tier.upper()}") or None


def resolve(provider: str, tier: str) -> list[str]:
    """Model ids for (provider, tier), best-first: env-preferred (if any), then the
    scored candidates the key can actually see. Always returns ≥1 id."""
    prefer = _preferred(provider, tier)
    cands = sorted(providers.candidates(provider, tier), key=lambda kv: -kv[1])
    avail = available_ids(provider)
    ranked = [m for m, _ in cands if avail is None or m in avail]
    ordered = ([prefer] if prefer else []) + [m for m in ranked if m != prefer]
    if not ordered:                              # nothing available/known → best guess
        ordered = [prefer] if prefer else ([cands[0][0]] if cands else [])
    if (provider, tier) not in _logged:
        _logged.add((provider, tier))
        drop = [m for m, _ in cands if avail is not None and m not in avail]
        _LOG.info("models[%s/%s] → %s%s%s", provider, tier, ordered,
                  "  (pref)" if prefer else "",
                  f"  (indispo: {drop})" if drop else "")
    return ordered


def top(provider: str, tier: str) -> str:
    """Best candidate id WITHOUT a network check (for display/back-compat labels)."""
    prefer = _preferred(provider, tier)
    if prefer:
        return prefer
    cands = sorted(providers.candidates(provider, tier), key=lambda kv: -kv[1])
    return cands[0][0] if cands else providers.candidates("mistral", tier)[0][0]
