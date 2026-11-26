"""Action list in, result list out. Clicks use [data-agent-id], not coordinates.

COMPOSITES is the one mutable global. register_composite writes it at import.
A turn only reads it.
"""
from dataclasses import dataclass
from typing import Any, Callable
import config
from perception import dom_hash, pixels_differ
@dataclass
class Action:
    type: str
    params: dict[str, Any]
@dataclass
class ActionResult:
    success: bool
    reason: str = ""
COMPOSITES: dict[str, Callable] = {}
def register_composite(name: str):
    def decorator(fn):
        COMPOSITES[name] = fn
        return fn
    return decorator
@register_composite("noop")
def _noop(page, params):
    return [Action("wait", {"kind": "fixed", "milliseconds": 0})]
def execute_turn(page, actions: list[Action]) -> list[ActionResult]:
    return [_safe(page, action) for action in actions]
def _safe(page, action: Action) -> ActionResult:
    try:
        return _RUN[action.type](page, action.params or {})
    except Exception as exc:
        reason = "timeout" if "Timeout" in type(exc).__name__ else "exception"
        return ActionResult(False, reason)
def _loc(page, eid):
    return page.locator(f'[data-agent-id="{int(eid)}"]')
def _precheck(page, loc) -> str | None:
    if loc.count() == 0:
        return "no_element_found"
    box = loc.bounding_box()
    if not box or box["width"] < 2 or box["height"] < 2:
        try:
            loc.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            return "element_not_visible"
        box = loc.bounding_box()
        if not box or box["width"] < 2 or box["height"] < 2:
            return "element_not_visible"
    sx = int(float(loc.get_attribute("data-agent-x") or 0))
    sy = int(float(loc.get_attribute("data-agent-y") or 0))
    vp = page.viewport_size or config.VIEWPORT
    tol = config.POS_TOLERANCE
    if 0 <= sx < vp["width"] and 0 <= sy < vp["height"]:
        if abs(box["x"] - sx) > tol or abs(box["y"] - sy) > tol:
            return "element_at_wrong_position"
    return None
def _snap(page):
    return page.url, dom_hash(page), page.screenshot(type="png")
def _judge(page, before) -> ActionResult:
    url, digest, png = before
    if page.url != url or dom_hash(page) != digest:
        return ActionResult(True, "")
    if pixels_differ(png, page.screenshot(type="png")):
        return ActionResult(False, "no_dom_change")
    return ActionResult(False, "no_screen_change")
def _ready(page, params):
    loc = _loc(page, params["id"])
    err = _precheck(page, loc)
    return loc, err, None if err else _snap(page)
def _click(page, params):
    loc, err, before = _ready(page, params)
    if err:
        return ActionResult(False, err)
    loc.click(timeout=3000)
    page.wait_for_timeout(100)
    return _judge(page, before)
def _type(page, params):
    loc, err, before = _ready(page, params)
    if err:
        return ActionResult(False, err)
    text = str(params.get("text", ""))
    loc.fill(text, timeout=3000)
    if params.get("submit"):
        loc.press("Enter")
        page.wait_for_timeout(150)
    judged = _judge(page, before)
    if judged.success:
        return judged
    try:
        if loc.input_value() == text:
            return ActionResult(True, "")
    except Exception:
        pass
    return judged
def _select(page, params):
    loc, err, before = _ready(page, params)
    if err:
        return ActionResult(False, err)
    option = str(params.get("option", ""))
    try:
        loc.select_option(value=option, timeout=2000)
    except Exception:
        loc.select_option(label=option, timeout=2000)
    judged = _judge(page, before)
    if judged.success or loc.input_value() == option:
        return ActionResult(True, "")
    return judged
def _other(page, kind, params):
    if kind in ("done", "approval_needed"):
        return ActionResult(kind == "done", "" if kind == "done" else "exception")
    if kind == "wait":
        if params.get("kind") == "network_idle":
            page.wait_for_load_state("networkidle", timeout=5000)
        else:
            page.wait_for_timeout(int(params.get("milliseconds") or 0))
        return ActionResult(True, "")
    if kind == "goto":
        before = page.url
        page.goto(str(params.get("url", "")), wait_until="domcontentloaded", timeout=5000)
        ok = page.url != before
        return ActionResult(ok, "" if ok else "no_url_change")
    if kind == "key":
        before = _snap(page)
        page.keyboard.press(str(params.get("key", "Enter")))
        page.wait_for_timeout(100)
        return _judge(page, before)
    y = page.evaluate("() => window.scrollY")
    eid = params.get("id")
    if eid is None:
        page.mouse.wheel(0, 500 if params.get("direction", "down") == "down" else -500)
    elif _loc(page, eid).count() == 0:
        return ActionResult(False, "no_element_found")
    else:
        _loc(page, eid).scroll_into_view_if_needed(timeout=2000)
    page.wait_for_timeout(100)
    moved = page.evaluate("() => window.scrollY") != y
    return ActionResult(moved, "" if moved else "no_screen_change")
def _composite(page, params):
    fn = COMPOSITES.get(str(params.get("name", "")))
    if fn is None:
        return ActionResult(False, "exception")
    inner = execute_turn(page, list(fn(page, params.get("params") or {})))
    failed = next((item for item in inner if not item.success), None)
    return failed or ActionResult(bool(inner), "" if inner else "exception")
def _bind(kind):
    return lambda page, params: _other(page, kind, params)
_RUN = {"click_element": _click, "type": _type, "select": _select, "composite": _composite}
_RUN.update({kind: _bind(kind) for kind in ("key", "scroll", "goto", "wait", "done", "approval_needed")})
def register_action(kind, fn):
    _RUN[kind] = fn
