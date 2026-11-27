"""Execute one planned subgoal against the page. No Playwright import.

Deterministic subgoals return their action and the loop does not call decide.
A commit subgoal spends one read-only turn first. Clicks on that turn are dropped.
"""
from actions import Action
from eval_checks import run_check
from plan import current, on_fail, on_pass, resolve

_KEEP = {"wait", "scroll"}


def scripted_actions(state):
    sub = current(state)
    if not sub or not sub.get("deterministic") or state.plan.get("phase") == "review":
        return None
    action = sub["action"]
    return [Action(action["type"], dict(action.get("params") or {}))]


def capture(state, actions) -> None:
    if not getattr(state, "plan", None):
        return
    for action in actions:
        if action.type == "say":
            state.plan["statement"] = str(action.params.get("text") or "")


def executable(state, actions):
    sub = current(state)
    if not sub:
        return actions
    phase = state.plan.get("phase")
    if state.plan.get("hold") and phase == "act":
        return [action for action in actions if action.type in _KEEP]
    if not sub.get("commit") or phase != "review":
        return actions
    return [action for action in actions if action.type in _KEEP]


def mark_url(state, page) -> None:
    plan = getattr(state, "plan", None)
    if not plan or plan.get("status") != "run":
        return
    key = (plan.get("index"), plan.get("phase"), plan.get("replans"))
    if plan.get("marked") != key:
        plan["url_at_start"] = page.url
        plan["marked"] = key


def _mapped(check, state):
    if not isinstance(check, dict):
        return None
    fields = {}
    for key, value in check.items():
        if not isinstance(value, str):
            fields[key] = value
            continue
        resolved = resolve(value, state.notes)
        if resolved is None:
            return None
        fields[key] = resolved
    kind = fields.get("type")
    if kind == "value_equals":
        selector = fields.get("selector") or ("#" + str(fields.get("id") or ""))
        return "input_value", {"selector": selector, "value": fields.get("value", "")}
    if kind in ("url_changed", "enabled"):
        return kind, fields
    return kind, {key: value for key, value in fields.items() if key != "type"}


def run_spec(page, check, state) -> bool:
    mapped = _mapped(check, state)
    if mapped is None:
        return False
    name, args = mapped
    if name == "url_changed":
        start = (state.plan or {}).get("url_at_start") or ""
        return bool(start) and page.url != start
    if name == "enabled":
        from plan_gate import enabled
        return enabled(page, args)
    if name not in ("url_contains", "input_value", "text_visible", "checked", "select_value", "approval_held"):
        return False
    return bool(run_check(page, name, args, state))


_SECRET_IDS = {"code", "otp", "password", "secret", "pin"}


def _hidden(page, check) -> bool:
    """Vault values, password fields, and code-like ids stay out of notes."""
    from logger import held
    if not isinstance(check, dict):
        return False
    value = str(check.get("value") or "")
    if value and value in held():
        return True
    eid = str(check.get("id") or "")
    if eid.lower() in _SECRET_IDS:
        return True
    if not eid:
        return False
    loc = page.locator(f"#{eid}")
    if not loc.count():
        return False
    el = loc.first
    if (el.get_attribute("data-agent-secret") or "") == "1":
        return True
    kind = (el.get_attribute("type") or "").lower()
    name = (el.get_attribute("name") or "").lower()
    return kind == "password" or name in _SECRET_IDS


def _keep(state, check, page) -> str:
    from logger import scrub
    result = on_pass(state, check)
    if _hidden(page, check):
        key = str(check.get("note") or check.get("id") or "")
        if key and state.notes:
            state.notes.pop(key, None)
    state.notes = scrub(dict(state.notes or {}))
    return result


def settle(state, page) -> bool:
    """True means the episode should stop."""
    sub = current(state)
    if sub is None:
        return True
    if state.plan.get("phase") == "review":
        if not run_spec(page, sub.get("review"), state):
            return on_fail(state, "review") == "stop"
        pre = sub.get("precondition")
        if pre and not run_spec(page, pre, state):
            why = state.plan.pop("hold", None) or "precondition"
            return on_fail(state, why) == "stop"
        return _keep(state, sub.get("review"), page) == "stop"
    hold = state.plan.pop("hold", None)
    if hold:
        return on_fail(state, hold) == "stop"
    if run_spec(page, sub.get("check"), state):
        return _keep(state, sub.get("check"), page) == "stop"
    return on_fail(state, "check") == "stop"
