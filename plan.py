"""Plan cursor. No plan keeps the old planner.

{row.field} and {base} bind at attach. {notes.field} resolves only after a value check accepts it. A failed check retries that subgoal once, in place, then the episode stops.
"""
CHECKS = {"url_contains", "input_value", "text_visible", "checked", "select_value", "value_equals", "url_changed", "enabled"}


def _ok(node) -> bool:
    return isinstance(node, dict) and node.get("type") in CHECKS


def validate(plan) -> list[str]:
    subs = plan.get("subgoals") if isinstance(plan, dict) else None
    if not isinstance(subs, list) or not subs:
        return ["subgoals"]
    errors = []
    for index, sub in enumerate(subs):
        if not isinstance(sub, dict) or not str(sub.get("text") or "").strip():
            errors.append(f"{index}.shape")
            continue
        if not _ok(sub.get("check")):
            errors.append(f"{index}.check")
        action = sub.get("action")
        if sub.get("deterministic") and (not isinstance(action, dict) or not action.get("type")):
            errors.append(f"{index}.action")
        if sub.get("commit") and not _ok(sub.get("review")):
            errors.append(f"{index}.review")
        if "precondition" in sub and not _ok(sub.get("precondition")):
            errors.append(f"{index}.precondition")
    return errors


def slots_for(row=None, base=None) -> dict:
    slots = {} if base is None else {"base": base}
    for key, value in (row or {}).items():
        slots[f"row.{key}"] = value
    return slots


def _fill(node, slots):
    if isinstance(node, str):
        for key, value in slots.items():
            node = node.replace("{" + key + "}", str(value))
        return node
    if isinstance(node, dict):
        return {key: _fill(value, slots) for key, value in node.items()}
    if isinstance(node, list):
        return [_fill(value, slots) for value in node]
    return node


def resolve(text, notes):
    text = str(text if text is not None else "")
    notes = notes or {}
    cursor = 0
    parts = []
    while True:
        start = text.find("{notes.", cursor)
        if start < 0:
            return "".join(parts) + text[cursor:]
        end = text.find("}", start)
        key = text[start + 7:end]
        if end < 0 or key not in notes:
            return None
        parts.append(text[cursor:start] + str(notes[key]))
        cursor = end + 1


def attach(state, plan, slots=None) -> None:
    errors = validate(plan)
    if errors:
        raise ValueError(",".join(errors))
    spec = _fill(plan, slots or {})
    state.plan = {
        "spec": spec, "index": 0, "replans": 0, "results": [], "statement": "", "status": "run",
        "phase": "review" if spec["subgoals"][0].get("commit") else "act",
    }
    state.notes = {}
    state.subgoal = subgoal_text(state)


def _subs(plan):
    return (plan.get("spec") or {}).get("subgoals") or []


def subgoal_text(state) -> str:
    plan = state.plan or {}
    if plan.get("status") in ("done", "failed"):
        return "done"
    subs = _subs(plan)
    index = int(plan.get("index") or 0)
    if index >= len(subs):
        return "done"
    if plan.get("phase") == "review":
        return "Review: " + subs[index]["text"]
    return subs[index]["text"]


def current(state):
    plan = getattr(state, "plan", None)
    if not plan or plan.get("status") != "run":
        return None
    subs = _subs(plan)
    index = int(plan.get("index") or 0)
    return subs[index] if index < len(subs) else None


def _note(state, check):
    if not isinstance(check, dict) or check.get("type") not in ("value_equals", "input_value"):
        return
    key = check.get("note") or check.get("id")
    if key and check.get("value") is not None:
        state.notes[str(key)] = check.get("value")


def on_pass(state, check) -> str:
    _note(state, check)
    plan = state.plan
    if plan.get("phase") == "review":
        plan["phase"] = "act"
        state.subgoal = subgoal_text(state)
        return "continue"
    sub = current(state)
    plan["results"].append({"text": sub["text"], "passed": True})
    plan["index"] += 1
    subs = _subs(plan)
    if plan["index"] >= len(subs):
        plan["status"] = "done"
        state.subgoal = "done"
        return "stop"
    plan["phase"] = "review" if subs[plan["index"]].get("commit") else "act"
    state.subgoal = subgoal_text(state)
    return "continue"


def on_fail(state, reason) -> str:
    plan = state.plan
    sub = current(state) or {}
    text = sub.get("text") or ""
    plan["results"].append({"text": text, "passed": False, "reason": reason})
    state.last_failure = {"action": {"type": "check", "params": {"text": text}}, "reason": reason}
    if plan["replans"] < 1:
        plan["replans"] += 1
        state.subgoal = subgoal_text(state)
        return "continue"
    plan["status"] = "failed"
    state.subgoal = "done"
    return "stop"
