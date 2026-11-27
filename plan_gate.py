"""Enabled means the control can be used. A retry may wait for that.

Not disabled, not aria-disabled="true", and not aria-busy="true".
Before a retry the loop waits up to 3s and checks again. Still busy is
"precondition: busy", which is not a failed value check.
"""
import time

WAIT_MS = 3000


def _locator(page, check):
    selector = (check or {}).get("selector") or ("#" + str((check or {}).get("id") or ""))
    return page.locator(selector)


def status(page, check) -> str:
    if not isinstance(check, dict) or check.get("type") != "enabled":
        return "missing"
    loc = _locator(page, check)
    if loc.count() == 0:
        return "missing"
    el = loc.first
    if not el.is_enabled():
        return "disabled"
    if (el.get_attribute("aria-disabled") or "").lower() == "true":
        return "disabled"
    if (el.get_attribute("aria-busy") or "").lower() == "true":
        return "busy"
    return "ok"


def enabled(page, check) -> bool:
    return status(page, check) == "ok"


def wait_enabled(page, check, timeout_ms: int = WAIT_MS) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while True:
        if status(page, check) == "ok":
            return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(100)


def prepare(state, page) -> None:
    """On a retry, wait for an enabled precondition. A busy control is held."""
    plan = getattr(state, "plan", None)
    if not plan or plan.get("status") != "run":
        return
    plan.pop("hold", None)
    from plan import current
    sub = current(state) or {}
    pre = sub.get("precondition")
    if not isinstance(pre, dict) or pre.get("type") != "enabled":
        return
    if plan.get("replans", 0) >= 1 and plan.get("waited") != plan.get("replans"):
        wait_enabled(page, pre)
        plan["waited"] = plan.get("replans")
    kind = status(page, pre)
    if kind != "ok":
        plan["hold"] = "precondition: busy" if kind == "busy" else "precondition"
