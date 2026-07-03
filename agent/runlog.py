"""
Run logging — make the pipeline's behaviour easy to check after the fact.

Answers the questions that bit us silently before:
  • WHICH provider / model / API key actually served each call? (caught the
    "everything silently ran on the Mistral fallback" bug)
  • When did a key rotate or a provider fail over, and why?
  • What tools did the Analyste call, in what order?
  • Which reviewer findings fired?

Everything is timestamped to `agent/out/run.log` (append) and echoed concisely to
stderr. `served_summary()` returns the per-(provider,model) success tally so a run
can end with a one-line "served by …" proof.
"""
from __future__ import annotations

import os
import logging
from collections import Counter

from langchain_core.callbacks import BaseCallbackHandler

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "out", "run.log")

_SERVED: Counter = Counter()   # (provider, model) -> successful calls
_log: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """The shared 'nexa' logger — file (DEBUG) + stderr (INFO), configured once."""
    global _log
    if _log is not None:
        return _log
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lg = logging.getLogger("nexa")
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    if not lg.handlers:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                          "%Y-%m-%d %H:%M:%S"))
        lg.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("      · %(message)s"))
        lg.addHandler(sh)
    _log = lg
    return lg


# ---- LLM call accounting (called by analyste's rotation mixin) --------------
def record_served(provider: str, model: str) -> None:
    _SERVED[(provider, model)] += 1


def served_summary() -> dict:
    return {f"{p}/{m}": n for (p, m), n in _SERVED.most_common()}


def reset_served() -> None:
    _SERVED.clear()


# ---- tool-call visibility for the agent -------------------------------------
class ToolLogger(BaseCallbackHandler):
    """Logs each tool the agent invokes (name + args) and the result size."""

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = (serialized or {}).get("name", "?")
        get_logger().info("tool → %s(%s)", name, str(input_str)[:160])

    def on_tool_end(self, output, **kwargs):
        get_logger().debug("tool ← %d chars", len(str(output)))

    def on_tool_error(self, error, **kwargs):
        get_logger().warning("tool ✗ %s: %s", type(error).__name__, str(error)[:120])
