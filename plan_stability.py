"""Adapter for stability_run.py. decide() follows the bound plan.

This is not the 28-task heuristic. That heuristic never sees the row values.
Seed only names the log. The actions do not use it.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = str(Path(__file__).resolve().parent)
sys.path.insert(0, _ROOT)
if "config" in sys.modules and not hasattr(sys.modules["config"], "FIXTURES"):
    del sys.modules["config"]

import config
from actions import Action
from agent import run_episode as loop
from approver import approve
from plan import attach, slots_for
from state import TaskState

_httpd = None
_browser = None
_play = None


def _server():
    global _httpd
    if _httpd is None:
        from eval_runner import serve
        _httpd = serve()
    return _httpd


def _chrome():
    global _browser, _play
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _play = sync_playwright().start()
        _browser = _play.chromium.launch(headless=True)
    return _browser


def _values(spec) -> dict:
    found = {}
    for sub in spec["subgoals"]:
        for key in ("check", "review"):
            check = sub.get(key) or {}
            if check.get("type") == "value_equals" and check.get("id"):
                found[str(check["id"])] = str(check["value"])
    return found


def _decide(spec):
    values = _values(spec)

    def decide(obs, state):
        text = state.subgoal or ""

        def one(pred):
            return next(el["id"] for el in obs.elements if pred(el))

        if text.startswith("Fill"):
            actions = []
            for eid, value in values.items():
                if eid == "role":
                    continue
                match = [el for el in obs.elements if el["tag"] == "input" and eid.lower() in (el.get("text") or "").lower()]
                if match:
                    actions.append(Action("type", {"id": match[0]["id"], "text": value}))
            return actions or [Action("wait", {"kind": "fixed", "milliseconds": 0})]
        if text.startswith("Choose"):
            return [Action("select", {"id": one(lambda el: el["tag"] == "select"), "option": values.get("role", "Admin")})]
        if text.startswith("Review:"):
            return [Action("say", {"text": "Reviewing the form"})]
        if text.startswith("Review"):
            return [Action("wait", {"kind": "fixed", "milliseconds": 0})]
        if "Save" in text:
            button = one(lambda el: el["tag"] == "button" and (el.get("text") or "").strip() == "Save")
            return [Action("click_element", {"id": button})]
        return [Action("wait", {"kind": "fixed", "milliseconds": 0})]

    return decide


def _flags(results) -> list[bool]:
    order, last = [], {}
    for row in results or []:
        if row["text"] not in last:
            order.append(row["text"])
        last[row["text"]] = bool(row["passed"])
    return [last[text] for text in order]


def run_episode(url, plan_path, init_script, seed):
    """One planned episode. url is unused; the fixture server is the page."""
    del url
    http = _server()
    port = http.server_address[1]
    base = f"http://127.0.0.1:{port}"
    spec = json.loads(open(plan_path, encoding="utf-8").read())
    config.LOG_PATH = config.LOG_DIR / f"stability_{seed}.jsonl"
    if config.LOG_PATH.exists():
        config.LOG_PATH.unlink()
    ctx = _chrome().new_context(viewport=config.VIEWPORT, device_scale_factor=1)
    try:
        if init_script:
            ctx.add_init_script(init_script)
        page = ctx.new_page()
        page.goto(f"{base}/home.html")
        state = TaskState(spec["goal"], spec["goal"], 0, [], [], None, "plan-stub", None)
        attach(state, spec, slots_for({"name": "Ada", "email": "ada@example.com", "role": "Admin"}, base))
        loop(page, state, _decide(state.plan["spec"]), approve, 8)
        try:
            hits = list(page.evaluate("window.__decoy_hits || []"))
        except Exception:
            hits = ["page_gone"]
        status = (state.plan or {}).get("status")
        return SimpleNamespace(
            subgoal_passed=_flags((state.plan or {}).get("results")),
            completed=status == "done",
            decoy_hits=hits,
            stopped_before_commit=status == "failed",
            error=None,
        )
    finally:
        ctx.close()
