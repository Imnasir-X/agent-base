"""Deny risky clicks unless a person allows them.

Eval mode returns False for a risky target. Interactive mode asks on stdin.
Bare "Confirm" is not risky: the modal fixture uses that label. "confirm order" is.
"""
import os

_WORDS = ("checkout", "pay", "delete", "send")
_PHRASES = ("submit order", "confirm order")


def _labels(actions, observation) -> str:
    by_id = {el["id"]: (el.get("text") or "") for el in (observation.elements or [])}
    parts = []
    for action in actions:
        params = action.params or {}
        parts.append(str(params.get("text") or ""))
        parts.append(by_id.get(params.get("id"), ""))
    return " ".join(parts).lower()


def is_risky(actions, observation) -> bool:
    text = _labels(actions, observation)
    if any(phrase in text for phrase in _PHRASES):
        return True
    tokens = set(text.split())
    return any(word in tokens for word in _WORDS)


def approve(actions, observation, mode: str | None = None) -> bool:
    mode = mode or os.environ.get("HARNESS_APPROVER", "eval")
    if not is_risky(actions, observation):
        return True
    if mode == "interactive":
        print("Approve this action? [y/N]", flush=True)
        return input().strip().lower() in ("y", "yes")
    return False
