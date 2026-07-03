"""
LLM engine — provider/model selection, API-key rotation, rate limiting and
fallback, decoupled from any domain logic.

This used to live inside `analyste.py`, tangled with that agent's tools, schema
and prompt. It is now its own module so:
  • the Analyste is a thin domain layer (tools + schema + prompt) on top of it;
  • `reviewer.py` and the pipeline stages import LLM builders WITHOUT dragging the
    whole tool/agent module along;
  • adding a provider is a single entry in `providers.PROVIDERS` — nothing here
    changes (no if/elif per provider anywhere).

The three quota defences (free tiers cap tokens-per-minute AND tokens-per-day, and
the pipeline fires several stages back-to-back):
  1. a rate limiter PER PROVIDER spaces calls out;
  2. a PRIORITISED LIST OF KEYS per provider — a call rotates to the next key when
     the current one hits its TOKEN quota (TPM/TPD); a requests-per-interval limit
     (RPM/RPD) just waits & retries on the same key (see `_RotateOnTokenLimit`);
  3. a PROVIDER PRIORITY order (config- or env-driven) — later providers' keys are
     appended to the chain, so ONE run can span several providers' quotas.

Priority / rotation is now explicit and configurable:
  • PROVIDER order  → config.yaml `llm.provider_priority`, or env
    LLM_PROVIDER_PRIORITY="groq,mistral,gemini"; else [LLM_PROVIDER, LLM_FALLBACK_PROVIDER].
  • KEY order within a provider → env position, or an inline "key|N" priority
    (see `providers.keys`). Lower N tried first.
"""
from __future__ import annotations

import os
import re
import sys
import time
import random

import yaml
from dotenv import load_dotenv
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain.agents import create_agent

import providers
import models
from runlog import get_logger, record_served

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(HERE, "config.yaml")
load_dotenv(os.path.join(ROOT, ".env"))
_LOG = get_logger()

# ---- provider selection (set LLM_PROVIDER in .env: gemini|groq|mistral|deepseek) ----
PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
FALLBACK_PROVIDER = os.environ.get("LLM_FALLBACK_PROVIDER", "").lower().strip()

LLM_RPS = float(os.environ.get("LLM_RPS", "0.5"))          # 1 request / 2 s
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "6"))


# ------------------------------------------------------------- provider priority
def _config_provider_priority() -> list[str]:
    """`llm.provider_priority` from config.yaml, or [] if absent/unreadable."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        order = (cfg.get("llm") or {}).get("provider_priority") or []
        return [str(p).lower() for p in order]
    except Exception:
        return []


def provider_priority() -> list[str]:
    """Ordered providers a single call may traverse, best-first. Resolution:
    env LLM_PROVIDER_PRIORITY (csv) > config.yaml llm.provider_priority >
    [LLM_PROVIDER, LLM_FALLBACK_PROVIDER]. Unknown/duplicate names are dropped."""
    env = os.environ.get("LLM_PROVIDER_PRIORITY", "").strip()
    if env:
        order = [p for p in re.split(r"[\s,]+", env.lower()) if p]
    else:
        order = _config_provider_priority()
    if not order:
        order = [PROVIDER] + ([FALLBACK_PROVIDER]
                              if FALLBACK_PROVIDER and FALLBACK_PROVIDER != PROVIDER else [])
    seen, out = set(), []
    for p in order:
        if p in providers.PROVIDERS and p not in seen:
            seen.add(p)
            out.append(p)
    return out or [PROVIDER]


# ----------------------------------------------------------------- rate limiter
_LIMITERS: dict = {}


def _limiter(provider: str) -> InMemoryRateLimiter:
    """One limiter per provider — different providers have independent limits."""
    if provider not in _LIMITERS:
        _LIMITERS[provider] = InMemoryRateLimiter(
            requests_per_second=LLM_RPS, check_every_n_seconds=0.1, max_bucket_size=1)
    return _LIMITERS[provider]


# --------------------------------------------------------- error classification
def _status_code(exc: Exception):
    return getattr(exc, "status_code", None) or getattr(exc, "code", None)


def _is_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "resourceexhausted" in name:
        return True
    if str(_status_code(exc)) == "429":
        return True
    msg = str(exc).lower()
    return any(s in msg for s in ("429", "rate limit", "resource_exhausted", "quota"))


def _is_token_limit(exc: Exception) -> bool:
    """True for a rate-limit rejection driven by a TOKEN quota (TPM/TPD) — the
    only condition that rotates to the next key. Requests-per-interval limits
    (RPM/RPD) mention 'request', not 'token', so they return False."""
    return _is_rate_limit(exc) and "token" in str(exc).lower()


def _is_server_error(exc: Exception) -> bool:
    try:
        return 500 <= int(_status_code(exc)) < 600
    except (TypeError, ValueError):
        return False


def _backoff_seconds(attempt: int) -> float:
    return min(2.0 * (2 ** attempt), 60.0) + random.uniform(0, 0.5)


# ------------------------------------------------------------- rotation policy
class _RotateOnTokenLimit:
    """Chat-model mixin owning the retry/rotation policy (SDK retry is disabled,
    max_retries=0, so this is the single source of truth):
      * TOKEN quota (TPM/TPD)          -> raise now → `.with_fallbacks` rotates key.
      * requests-per-interval / 5xx    -> wait & retry on the SAME key (the quota
                                          refills; rotating would waste a key).
      * anything else (auth, 4xx, …)   -> raise now (fallback may rotate as a last
                                          resort, but we don't retry a dead key)."""

    def _tag(self):
        return _MODEL_META.get(id(self), ("?", "?", "?"))

    def _served(self, attempt):
        prov, mdl, ki = self._tag()
        record_served(prov, mdl)
        _LOG.info("LLM ✓ %s/%s key#%s%s", prov, mdl, ki,
                  f" (après {attempt} retry)" if attempt else "")

    def _failed(self, exc, attempt, rotating):
        prov, mdl, ki = self._tag()
        _LOG.warning("LLM ✗ %s/%s key#%s → %s: %s%s", prov, mdl, ki,
                     type(exc).__name__, str(exc)[:90],
                     "  → rotation/fallback" if rotating else f"  → retry {attempt+1}")

    def _generate(self, *args, **kwargs):
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                res = super()._generate(*args, **kwargs)
                self._served(attempt)
                return res
            except Exception as exc:
                retryable = (not _is_token_limit(exc)) and attempt < LLM_MAX_RETRIES \
                    and (_is_rate_limit(exc) or _is_server_error(exc))
                self._failed(exc, attempt, rotating=not retryable)
                if not retryable:
                    raise
                time.sleep(_backoff_seconds(attempt))

    async def _agenerate(self, *args, **kwargs):
        import asyncio
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                res = await super()._agenerate(*args, **kwargs)
                self._served(attempt)
                return res
            except Exception as exc:
                retryable = (not _is_token_limit(exc)) and attempt < LLM_MAX_RETRIES \
                    and (_is_rate_limit(exc) or _is_server_error(exc))
                self._failed(exc, attempt, rotating=not retryable)
                if not retryable:
                    raise
                await asyncio.sleep(_backoff_seconds(attempt))


_ROTATING: dict = {}


def _rotating(cls):
    """Cached `(_RotateOnTokenLimit, cls)` subclass — a real chat model (keeps
    bind_tools / with_structured_output) with the rotation policy layered in."""
    sub = _ROTATING.get(cls)
    if sub is None:
        sub = type(f"Rotating{cls.__name__}", (_RotateOnTokenLimit, cls), {})
        _ROTATING[cls] = sub
    return sub


# identity tag per built model instance, so the rotation mixin can log/record
# exactly which provider/model/key served (or failed) a given call.
_MODEL_META: dict = {}


def _chat(provider: str, key: str, model: str,
          temperature: float = 0, key_idx: int = 0):
    """One chat model bound to a SPECIFIC key + model id, built entirely from the
    provider registry (chat class, key kwarg, extra kwargs). max_retries=0: the
    rotation mixin owns retries."""
    spec = providers.spec(provider)
    cls = spec["cls"]()                                    # lazy SDK import
    common = dict(model=model, temperature=temperature,
                  rate_limiter=_limiter(provider), max_retries=0)
    m = _rotating(cls)(**{spec["key_kwarg"]: key}, **spec.get("extra", {}), **common)
    _MODEL_META[id(m)] = (provider, model, key_idx)
    return m


def _leaf_models(tier: str, temperature: float) -> list:
    """One chat model per (provider, model, key), in FALLBACK ORDER: for each
    provider in `provider_priority()`, its best-scored available model across every
    key (priority-ordered), then the next model, then the next provider.
    `.with_fallbacks` walks this list, advancing on a token limit. EACH provider
    uses ITS OWN model for `tier` (so the fallback never inherits a name that
    doesn't exist on it)."""
    out = []
    for provider in provider_priority():
        keys = providers.keys(provider)
        if not keys:
            env = providers.spec(provider)["key_env"]
            sys.exit(f"ERREUR : {env}(S) absent de .env "
                     f"(provider={provider} ; voir .env.example).")
        # try the best-scored available model first (all keys), then the next, …
        for model in models.resolve(provider, tier):
            out += [_chat(provider, k, model, temperature=temperature, key_idx=j)
                    for j, k in enumerate(keys)]
    return out


def build_model(tier: str = "small", temperature: float = 0):
    """Chat model for the active provider at `tier` ('small'|'big'); fails over
    across every configured API key (and the fallback providers' keys), each
    using its own model for that tier."""
    leaves = _leaf_models(tier, temperature)
    return leaves[0] if len(leaves) == 1 else leaves[0].with_fallbacks(leaves[1:])


def build_structured(schema, tier: str = "small", temperature: float = 0):
    """Like build_model but for a structured-output call (Stratège/Rédacteur):
    `.with_structured_output(schema)` on each key's model, chained with fallback."""
    runs = [m.with_structured_output(schema)
            for m in _leaf_models(tier, temperature)]
    return runs[0] if len(runs) == 1 else runs[0].with_fallbacks(runs[1:])


def _failover_excs() -> tuple:
    """Exceptions that mean 'this model/key failed → try the next one': quota/rate
    limits, incompatible request (400 json+tools), auth, timeouts, server errors.
    Deliberately EXCLUDES GraphRecursionError — an agent loop is not a provider
    fault, so re-running it on every other key/model just burns quota to hit the
    same wall; it must propagate. Built from whichever provider SDKs are installed."""
    excs: list = []
    for mod in ("openai", "groq", "mistralai"):
        try:
            m = __import__(mod)
            excs += [getattr(m, n) for n in
                     ("RateLimitError", "APIStatusError", "APIError",
                      "BadRequestError", "AuthenticationError", "APITimeoutError")
                     if hasattr(m, n)]
        except Exception:
            pass
    # google-genai raises ResourceExhausted/GoogleAPIError (not an openai-style base)
    try:
        from google.api_core import exceptions as g
        excs += [g.ResourceExhausted, g.GoogleAPIError]
    except Exception:
        pass
    return tuple(excs) or (Exception,)


def build_agent(tools, system_prompt: str, response_format,
                tier: str = "big", temperature: float = 0):
    """A tool-using `create_agent` for the given tools/prompt/schema. `create_agent`
    needs a bind_tools-capable model (a fallback chain isn't one), so we build ONE
    agent per (provider, model, key) and fail the AGENTS over: a token limit / 400 /
    auth failure restarts the agent on the next key/model. A GraphRecursionError is
    EXCLUDED (it's a loop, not a provider fault) so it propagates instead of
    cascading across every key."""
    agents = [create_agent(m, tools=tools, system_prompt=system_prompt,
                           response_format=response_format)
              for m in _leaf_models(tier, temperature)]
    if len(agents) == 1:
        return agents[0]
    return agents[0].with_fallbacks(agents[1:], exceptions_to_handle=_failover_excs())


# --------------------------------------------------------------- thinking mode
def thinking_available(provider: str) -> bool:
    """True if `provider` declares a reasoning mode (providers.thinking_spec)."""
    return providers.thinking_spec(provider) is not None


def _thinking_chat(provider: str, key: str, tspec: dict, key_idx: int = 0):
    """A rotating chat model on the provider's THINKING model + reasoning kwargs.
    No temperature (thinking mode ignores it); built from the registry like `_chat`."""
    spec = providers.spec(provider)
    m = _rotating(spec["cls"]())(
        model=tspec["model"], rate_limiter=_limiter(provider), max_retries=0,
        **{spec["key_kwarg"]: key}, **spec.get("extra", {}), **tspec.get("kwargs", {}))
    _MODEL_META[id(m)] = (provider, tspec["model"], key_idx)
    return m


def build_thinking_agent(tools, system_prompt: str, provider: str | None = None):
    """A PLAIN tool agent (NO forced structured output) on the provider's thinking
    model, failing over across its keys. Returns None if the provider declares no
    thinking capability. Thinking mode supports auto tool-calls but not the forced
    tool_choice structured output needs — so the caller formats the result itself."""
    provider = provider or PROVIDER
    tspec = providers.thinking_spec(provider)
    if tspec is None:
        return None
    agents = [create_agent(_thinking_chat(provider, k, tspec, key_idx=j),
                           tools=tools, system_prompt=system_prompt)
              for j, k in enumerate(providers.keys(provider))]
    if not agents:
        return None
    if len(agents) == 1:
        return agents[0]
    return agents[0].with_fallbacks(agents[1:], exceptions_to_handle=_failover_excs())
