"""Fake decide(). Random mode has no task policy. Heuristic mode reads the task text.

Neither mode imports a model SDK. last_failure is read so a bad id is not repeated.
"""
import random
import re

import config
from actions import Action

_STOP = {"click", "the", "into", "and", "then", "press", "type", "select", "a", "submit", "enter"}
_TYPE = re.compile(r"type '([^']*)' into ([a-z0-9 ]+?)(?=,| and submit| and press|$)", re.I)
_SELECT = re.compile(r"select '([^']*)'", re.I)
_WORD = re.compile(r"[a-z0-9]+|[\u0980-\u09ff]+")


def decide(observation, state) -> list[Action]:
    if config.STUB_MODE == "random":
        return _random(observation, state)
    return [_heuristic(observation, state) or Action("done", {})]


def _failed_id(state):
    failure = state.last_failure or {}
    return ((failure.get("action") or {}).get("params") or {}).get("id")


def _random(observation, state) -> list[Action]:
    failed = _failed_id(state)
    elements = [el for el in observation.elements if el["id"] != failed]
    if not elements or state.step >= 4:
        return [Action("done", {})]
    pick = random.choice(elements)
    return [Action("click_element", {"id": pick["id"]})]


def _overlap(text, tokens) -> int:
    hay = (text or "").lower()
    return sum(token in hay for token in tokens)


def _tokens(text: str) -> list[str]:
    return [tok for tok in _WORD.findall(text.lower()) if tok not in _STOP]


def _heuristic(observation, state):
    elements = list(observation.elements)
    typed = _next_type(state, elements)
    if typed:
        return typed
    selected = _next_select(state, elements)
    if selected:
        return selected
    clause = _open_clause(state)
    if not clause:
        return None
    tokens = _tokens(clause)
    ranked = sorted(elements, key=lambda el: (-_overlap(el["text"], tokens), el["id"]))
    failed = _failed_id(state)
    for el in ranked:
        if el["id"] == failed or _overlap(el["text"], tokens) <= 0:
            continue
        return Action("click_element", {"id": el["id"], "text": el["text"]})
    return None


def _next_type(state, elements):
    pairs = [(text, field.strip()) for text, field in _TYPE.findall(state.task)]
    submit = "submit" in state.task.lower() or "press enter" in state.task.lower()
    for index, (text, field) in enumerate(pairs):
        if _done_type(state, field, text):
            continue
        fields = [el for el in elements if el["tag"] in ("input", "textarea")]
        tokens = _tokens(field)
        fields.sort(key=lambda el: (-_overlap(el["text"], tokens), el["id"]))
        if not fields or _overlap(fields[0]["text"], tokens) <= 0:
            return None
        if fields[0]["id"] == _failed_id(state):
            continue
        return Action("type", {
            "id": fields[0]["id"], "text": text, "field": field,
            "submit": submit and index == len(pairs) - 1,
        })
    return None


def _done_type(state, field, text) -> bool:
    for rec in state.completed:
        params = rec.get("params") or {}
        if rec.get("success") and rec.get("type") == "type" and params.get("text") == text:
            if str(params.get("field", "")).lower() == field.lower():
                return True
    return False


def _next_select(state, elements):
    match = _SELECT.search(state.task)
    if not match:
        return None
    option = match.group(1)
    for rec in state.completed:
        params = rec.get("params") or {}
        if rec.get("success") and rec.get("type") == "select" and params.get("option") == option:
            return None
    selects = [el for el in elements if el["tag"] == "select"]
    if not selects or selects[0]["id"] == _failed_id(state):
        return None
    return Action("select", {"id": selects[0]["id"], "option": option})


def _open_clause(state):
    parts = re.split(r"\bthen\b", state.task, flags=re.I)
    for part in parts:
        if "type '" in part.lower() or "select '" in part.lower():
            continue
        tokens = _tokens(part)
        if tokens and not _click_done(state, tokens):
            return part
    return None


def _click_done(state, tokens) -> bool:
    for rec in state.completed:
        params = rec.get("params") or {}
        if rec.get("success") and rec.get("type") == "click_element":
            if _overlap(params.get("text", ""), tokens) >= len(tokens):
                return True
    return False
