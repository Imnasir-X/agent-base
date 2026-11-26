"""Deny commits unless a person allows them.

Typing and reading are free. A commit needs approval: submit, Enter, a pay
or delete word, a Bangla pay label, or a button inside a delete or pay
dialog. Eval mode returns False and does not read stdin.
"""
import os

_WORDS = ("checkout", "pay", "payment", "delete", "send", "buy", "purchase", "submit", "order")
_PHRASES = ("place order", "buy now", "submit order", "confirm order")
_BANG = ("পেমেন্ট", "মুছ", "কিনুন", "অর্ডার")
_DANGER = ("delete", "pay", "payment", "checkout", "buy", "purchase", "order")


def _el(observation, eid) -> dict:
    for el in observation.elements or []:
        if el.get("id") == eid:
            return el
    return {}


def _blob(action, el) -> str:
    params = action.params or {}
    parts = [
        params.get("text") or "", params.get("key") or "",
        el.get("text") or "", el.get("context") or "", el.get("form_action") or "",
    ]
    return " ".join(str(part) for part in parts).lower()


def _words(text: str) -> bool:
    if any(phrase in text for phrase in _PHRASES):
        return True
    if any(piece in text for piece in _BANG):
        return True
    tokens = set(text.split())
    return any(word in tokens for word in _WORDS)


def _danger(text: str) -> bool:
    hay = (text or "").lower()
    if any(piece in hay for piece in _BANG):
        return True
    if any(word in hay.split() for word in _DANGER):
        return True
    return any(f"/{word}" in hay for word in _DANGER)


def is_risky(actions, observation) -> bool:
    for action in actions:
        params = action.params or {}
        if action.type in ("type", "fill_secret") and params.get("submit"):
            return True
        if action.type == "key" and str(params.get("key") or "").lower() in ("enter", "return"):
            return True
        if action.type not in ("click_element", "approval_needed"):
            continue
        el = _el(observation, params.get("id"))
        if el.get("submit"):
            return True
        blob = _blob(action, el)
        if _words(blob):
            return True
        if _danger(f"{el.get('context') or ''} {el.get('form_action') or ''}"):
            return True
    return False


def approve(actions, observation, mode: str | None = None) -> bool:
    mode = mode or os.environ.get("HARNESS_APPROVER", "eval")
    if not is_risky(actions, observation):
        return True
    if mode == "interactive":
        print("Approve this action? [y/N]", flush=True)
        return input().strip().lower() in ("y", "yes")
    return False
