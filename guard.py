"""Hard stops before a run touches a real site.

A step ceiling, a repeat-failure stop, and a domain allowlist. The loop
calls blocked() after observe and before the action runs.
"""
import os
from urllib.parse import urlparse


def ceiling() -> int:
    return int(os.environ.get("HARNESS_MAX_STEPS", "8"))


def allow_hosts() -> set[str]:
    raw = os.environ.get("HARNESS_ALLOW_DOMAINS", "127.0.0.1,localhost")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _same(rec: dict) -> tuple:
    params = rec.get("params") or {}
    return (rec.get("type"), str(params.get("id")), rec.get("reason"))


def repeated(state, limit: int = 3) -> bool:
    fails = list(state.failures or [])
    if len(fails) < limit:
        return False
    last = fails[-limit:]
    return len({_same(rec) for rec in last}) == 1


def blocked(state, observation) -> str | None:
    """Return a stop reason, or None when the turn may proceed."""
    if state.step >= ceiling():
        return "step_limit"
    if repeated(state):
        return "repeated_failure"
    host = (urlparse(getattr(observation, "url", "") or "").hostname or "").lower()
    if host and host not in allow_hosts():
        return "domain_blocked"
    return None
