"""
Provider registry — the SINGLE source of truth for each LLM provider's specifics.

Before this module the same provider knowledge was duplicated and scattered:
  • models._KEY_ENV  AND  analyste._PROVIDER_KEY_ENV  (the same mapping, twice);
  • models._CANDIDATES                                (scored models per tier);
  • models._fetch_ids                                 (an if/elif per provider);
  • analyste._chat                                    (another if/elif per provider).

Now ONE entry per provider in `PROVIDERS` holds it all, so **adding a provider is a
single dict entry** — no code changes in models.py / llm.py. Each entry declares:
  • key_env    — the env var holding its API key(s);
  • cls        — a lazy importer returning the LangChain chat class (import the SDK
                 only when the provider is actually used);
  • key_kwarg  — the constructor kwarg that receives the key (differs per SDK);
  • extra      — extra constructor kwargs (e.g. DeepSeek's OpenAI-compatible base_url);
  • list_ids   — fn(key) -> live model ids the key can see, or None if there is no
                 cheap list call (→ availability filter assumes all candidates ok);
  • candidates — per-tier [(model_id, score)] scored for OPERATIONAL fit (see below).

`keys()` is the ONE key parser: an env var may hold one or many keys (comma / space
/ newline separated), and a key may carry an inline PRIORITY as "key|N" (lower N =
tried first; unannotated keys keep their positional order). `<ENV>S` (plural) is
also honoured.
"""
from __future__ import annotations

import os
import re
import json


# --------------------------------------------------- lazy chat-class importers
# Return the LangChain chat class; the SDK is imported only on first use so a
# provider you never touch never needs its package installed.
def _gemini_cls():
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI


def _groq_cls():
    from langchain_groq import ChatGroq
    return ChatGroq


def _mistral_cls():
    from langchain_mistralai import ChatMistralAI
    return ChatMistralAI


def _openai_cls():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI


# ------------------------------------------------------ live model-list fetchers
def _groq_ids(key: str) -> list:
    from groq import Groq
    return sorted(m.id for m in Groq(api_key=key).models.list().data)


def _mistral_ids(key: str) -> list:
    import urllib.request
    req = urllib.request.Request("https://api.mistral.ai/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return sorted({m["id"] for m in json.load(r)["data"]})


def _deepseek_ids(key: str) -> list:
    import urllib.request
    req = urllib.request.Request("https://api.deepseek.com/models",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        ids = {m["id"] for m in json.load(r)["data"]}
    ids.add("deepseek-chat")     # valid alias not always returned by /models
    return sorted(ids)


# ================================================================== the registry
# score = suitability FOR THAT TIER (not absolute capability):
#   • "big"   (tool-using Analyste)        → favours reasoning/tool-calling strength;
#   • "small" (Stratège/Rédacteur/critique) → favours cheap+fast-but-adequate.
# Only tool-calling + JSON-mode compatible models are listed (Groq's gpt-oss and
# llama-4-scout are NOT — they 400 on "json mode + tools"). All ids confirmed present
# on live lists 2026-07-03; scores are heuristic — the availability filter + fallback
# chain make a wrong guess self-correcting rather than fatal.
#
# Measured Groq FREE-tier per-minute token limits (x-ratelimit-limit-tokens):
#   llama-3.3-70b = 12k TPM · qwen/qwen3-32b = 6k TPM · (TPD 100k/key/day either way).
# The tool-heavy Analyste request grows to ~14–16k tokens, so on FREE tier NO Groq
# model completes it (all 413 past their TPM → chain cascades to mistral-large). But
# llama-3.3-70b (12k) survives more turns than qwen (6k), so it ranks first for
# groq/big; qwen — smarter on paper but 413s after ONE tool call at 6k TPM — is only
# a low-priority groq/small candidate. On a paid Dev tier qwen could be promoted.
PROVIDERS: dict = {
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "cls": _gemini_cls,
        "key_kwarg": "google_api_key",
        "extra": {},
        "list_ids": None,                     # no cheap list call → assume all avail
        "candidates": {
            "big": [("gemini-2.5-flash", 82), ("gemini-2.5-flash-lite", 60)],
            "small": [("gemini-2.5-flash-lite", 82), ("gemini-2.5-flash", 60)],
        },
    },
    "groq": {
        "key_env": "GROQ_API_KEY",
        "cls": _groq_cls,
        "key_kwarg": "api_key",
        "extra": {},
        "list_ids": _groq_ids,
        # llama-4-scout is EXCLUDED: like gpt-oss it 400s on "json mode + tool
        # calling", which our agent needs together. Leaves llama-3.3-70b (12k TPM)
        # as the only viable groq/big, with qwen as a low-priority backstop.
        "candidates": {
            "big": [("llama-3.3-70b-versatile", 80),      # 12k TPM: survives most turns
                    ("qwen/qwen3-32b", 55)],              # 6k TPM: 413s after 1 tool call
            "small": [("llama-3.1-8b-instant", 82),       # fast+cheap = best "small"
                      ("llama-3.3-70b-versatile", 60),
                      ("qwen/qwen3-32b", 50)],
        },
    },
    "mistral": {
        "key_env": "MISTRAL_API_KEY",
        "cls": _mistral_cls,
        "key_kwarg": "api_key",
        "extra": {},
        "list_ids": _mistral_ids,
        "candidates": {
            "big": [("mistral-large-latest", 90),         # big context handles the
                    ("mistral-medium-latest", 80),        # tool-heavy Analyste
                    ("magistral-medium-latest", 78)],
            "small": [("mistral-small-latest", 82),
                      ("ministral-8b-latest", 60),
                      ("mistral-medium-latest", 50)],
        },
    },
    # DeepSeek (paid, OpenAI-compatible, 1M context → no TPM wall; cheap). We use
    # `deepseek-chat` (non-thinking) — the V4 thinking models (deepseek-v4-flash/
    # -pro) reject the forced tool_choice our structured output needs. `deepseek-chat`
    # retires 2026-07-24; revisit then. Same model both tiers — cheap enough and
    # strong at tool-calling. Reached via ChatOpenAI + the DeepSeek base_url.
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "cls": _openai_cls,
        "key_kwarg": "api_key",
        "extra": {"base_url": "https://api.deepseek.com"},
        "list_ids": _deepseek_ids,
        "candidates": {
            "big": [("deepseek-chat", 88)],
            "small": [("deepseek-chat", 80)],
        },
        # THINKING capability (opt-in via --deep/--thinking). A thinking-capable
        # model + the kwargs that enable reasoning. Thinking mode supports AUTO
        # tool-calls but NOT forced tool_choice, so the caller runs a plain tool
        # agent (no structured response_format) and formats the result separately.
        # Verified vs api-docs.deepseek.com/guides/thinking_mode (2026-07-03).
        # Any provider WITHOUT this key → thinking arg is a no-op (degrades).
        "thinking": {
            "model": "deepseek-v4-flash",
            "kwargs": {"extra_body": {"thinking": {"type": "enabled"}},
                       "reasoning_effort": "high"},   # temperature is ignored in thinking mode
        },
    },
}


def spec(provider: str) -> dict:
    """The registry entry for `provider` (raises a clear error if unknown)."""
    s = PROVIDERS.get(provider)
    if s is None:
        raise ValueError(f"provider inconnu '{provider}' — connus : "
                         f"{', '.join(PROVIDERS)}")
    return s


def candidates(provider: str, tier: str) -> list:
    """[(model_id, score)] for (provider, tier); [] if none declared."""
    return PROVIDERS.get(provider, {}).get("candidates", {}).get(tier, [])


def thinking_spec(provider: str) -> dict | None:
    """The provider's THINKING descriptor ({model, kwargs}), or None if it declares
    no reasoning mode → callers treat thinking as unavailable (a no-op)."""
    return PROVIDERS.get(provider, {}).get("thinking")


# ------------------------------------------------------------------------- keys
def _split(entry: str, idx: int) -> tuple[str, int]:
    """('key', priority) from a raw entry. 'key|N' sets priority N (lower = tried
    first); an unannotated key keeps its positional index as its priority."""
    if "|" in entry:
        key, _, prio = entry.rpartition("|")
        try:
            return key, int(prio)
        except ValueError:
            return entry, idx           # trailing '|' wasn't a number → literal key
    return entry, idx


def keys(provider: str) -> list[str]:
    """All configured API keys for `provider`, ordered by priority then position.
    Env var (singular, then <ENV>S plural) may hold one or many keys separated by
    comma / whitespace / newline; a key may carry an inline priority as 'key|N'."""
    env = spec(provider)["key_env"]
    raw = " ".join(v for v in (os.environ.get(env, ""),
                               os.environ.get(f"{env}S", "")) if v)
    entries = [e for e in re.split(r"[\s,]+", raw.strip()) if e]
    ranked = [(*_split(e, i), i) for i, e in enumerate(entries)]  # (key, prio, pos)
    ranked.sort(key=lambda kpp: (kpp[1], kpp[2]))                 # priority, then pos
    return [key for key, _prio, _pos in ranked]


def first_key(provider: str) -> str | None:
    """The highest-priority key for `provider` (for the availability probe)."""
    ks = keys(provider)
    return ks[0] if ks else None
