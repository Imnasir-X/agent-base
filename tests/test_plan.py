"""Planner cursor, the hand-written user template, and one local fixture.

users.html is not part of the 28-task list. No model is called.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


import sys
sys.path.insert(0, str(ROOT))

import config
from actions import Action
from agent import run_episode
from approver import approve
from plan import attach, slots_for, validate
from plan_report import measure
from planner_prompt import PROMPT
from state import TaskState

ROW = {"name": "Ada", "email": "ada@example.com", "role": "Admin"}
TEMPLATE = json.loads((ROOT / "plans" / "create_user.json").read_text(encoding="utf-8"))


def _find(obs, pred):
    return next(el["id"] for el in obs.elements if pred(el))


def _decide(page, names, calls, outs):
    pending = list(names)

    def decide(obs, state):
        calls.append(state.subgoal)
        text = state.subgoal
        if text.startswith("Fill"):
            name = _find(obs, lambda el: el["tag"] == "input" and "Name" in el["text"])
            email = _find(obs, lambda el: el["tag"] == "input" and "Email" in el["text"])
            return [
                Action("type", {"id": name, "text": pending.pop(0)}),
                Action("type", {"id": email, "text": ROW["email"]}),
            ]
        if text.startswith("Choose"):
            role = _find(obs, lambda el: el["tag"] == "select")
            return [Action("select", {"id": role, "option": "Admin"})]
        if text.startswith("Review:"):
            button = _find(obs, lambda el: el["tag"] == "button")
            return [
                Action("say", {"text": "Saving ada@example.com"}),
                Action("click_element", {"id": button}),
            ]
        if text.startswith("Review"):
            return [Action("wait", {"kind": "fixed", "milliseconds": 0})]
        if text == "Save user":
            outs.append(page.locator("#out").inner_text())
            button = _find(obs, lambda el: el["tag"] == "button")
            return [Action("click_element", {"id": button})]
        return [Action("done", {})]

    return decide


class TestPlanContract(unittest.TestCase):
    def test_template_and_prompt_and_measure(self):
        self.assertEqual(validate(TEMPLATE), [])
        tasks = json.loads((ROOT / "eval_tasks.json").read_text(encoding="utf-8"))
        self.assertNotIn("users.html", json.dumps(tasks))
        self.assertIn("value_equals", PROMPT)
        self.assertIn("Do not emit {notes.field}", PROMPT)
        self.assertNotIn("fill_secret", PROMPT)
        report = measure([
            {"success": True, "results": [
                {"text": "Fill", "passed": True}, {"text": "Save", "passed": True},
            ]},
            {"success": False, "results": [
                {"text": "Fill", "passed": False}, {"text": "Fill", "passed": True},
            ]},
        ])
        self.assertEqual(report["subgoal_pass_rate"], {"Fill": 1.0, "Save": 0.5})
        self.assertEqual(report["fixture_pass_rate"], 0.5)
        self.assertEqual(report["fixture_stdev"], 0.5)
        from plan_report import missing_slots, try_attach
        state = TaskState("Goal", "Goal", 0, [], [], None, "s", None)
        bad = {"subgoals": [{"text": "A", "check": {"type": "nope"}}]}
        self.assertFalse(try_attach(state, bad, {}))
        self.assertIsNone(state.plan)
        raw = {"subgoals": [{"text": "A", "check": {"type": "value_equals", "id": "name", "value": "{row.name}"}}]}
        self.assertEqual(missing_slots(raw, {}), ["row.name"])
        self.assertFalse(try_attach(state, raw, {}))
        self.assertTrue(try_attach(state, raw, {"row.name": "Ada"}))
        self.assertEqual(state.subgoal, "A")


class TestPlanRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from eval_runner import serve
        cls.httpd = serve()
        cls.port = cls.httpd.server_address[1]
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()
        cls.httpd.shutdown()

    def _page(self):
        ctx = self.browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{self.port}/home.html")
        return page

    def _run(self, names):
        page = self._page()
        path = config.LOG_DIR / "plan_create_user.jsonl"
        if path.exists():
            path.unlink()
        config.LOG_PATH = path
        state = TaskState(TEMPLATE["goal"], TEMPLATE["goal"], 0, [], [], None, "script", None)
        attach(state, TEMPLATE, slots_for(ROW, f"http://127.0.0.1:{self.port}"))
        calls, outs = [], []
        episode = run_episode(page, state, _decide(page, names, calls, outs), approve, 8)
        return page, state, episode, calls, outs

    def test_template_skips_the_open_and_reviews_before_save(self):
        page, state, episode, calls, outs = self._run(["Ada"])
        self.assertEqual(calls, [
            "Fill name and email from row 3",
            "Choose role Admin",
            "Review form before saving",
            "Review: Save user",
            "Save user",
        ])
        self.assertEqual(outs, [""])
        self.assertEqual(state.plan["statement"], "Saving ada@example.com")
        self.assertEqual(state.notes["name"], "Ada")
        self.assertEqual(state.notes["email"], ROW["email"])
        self.assertEqual(page.locator("#out").inner_text(), ROW["email"])
        self.assertIn("Ada", page.locator("#rows").inner_text())
        self.assertTrue(episode["success"])
        self.assertEqual(episode["replans"], 0)
        self.assertEqual(state.plan["status"], "done")

    def test_one_bad_name_replans_once(self):
        page, state, episode, calls, outs = self._run(["Nope", "Ada"])
        self.assertEqual(episode["replans"], 1)
        self.assertTrue(episode["success"], episode)
        self.assertEqual(page.locator("#name").input_value(), "Ada")
        self.assertEqual(calls[0], "Fill name and email from row 3")
        self.assertEqual(calls[1], "Fill name and email from row 3")

    def test_secret_fields_do_not_stay_in_notes(self):
        from logger import remember
        from plan_run import _keep
        page = self.browser.new_context().new_page()
        self.addCleanup(page.context.close)
        page.set_content("<input id='code' type='password' value='4419'><input id='name' value='Ada'>")
        state = TaskState("t", "t", 0, [], [], None, "s", None)
        state.notes = {}
        state.plan = {
            "phase": "act", "status": "run", "index": 0, "replans": 0, "results": [],
            "spec": {"subgoals": [{"text": "Code"}, {"text": "Name"}]},
        }
        _keep(state, {"type": "value_equals", "id": "code", "value": "4419"}, page)
        self.assertNotIn("code", state.notes)
        remember("vq7-note-secret")
        state.plan["index"] = 0
        state.plan["phase"] = "act"
        state.plan["status"] = "run"
        _keep(state, {"type": "value_equals", "id": "name", "value": "Ada vq7-note-secret"}, page)
        self.assertEqual(state.notes.get("name"), "Ada ***")
        self.assertNotIn("vq7-note-secret", json.dumps(state.notes))

    def test_select_fires_input_and_change(self):
        page = self.browser.new_context().new_page()
        self.addCleanup(page.context.close)
        page.set_content(
            "<select id='role'><option value=''>Choose</option><option value='Admin'>Admin</option></select>"
            "<button id='save' type='button' disabled>Save</button>"
            "<script>var seen=[]; var roleBox=document.getElementById('role');"
            "var saveButton=document.getElementById('save');"
            "roleBox.addEventListener('input', function(){ seen.push('input'); });"
            "roleBox.addEventListener('change', function(){ seen.push('change'); saveButton.disabled=false; });"
            "window.__seen=seen;</script>"
        )
        from perception import observe
        obs = observe(page)
        picked = next(el for el in obs.elements if el["tag"] == "select")
        from actions import execute_turn
        execute_turn(page, [Action("select", {"id": picked["id"], "option": "Admin"})])
        self.assertEqual(page.evaluate("window.__seen"), ["input", "change"])
        self.assertTrue(page.locator("#save").is_enabled())

    def test_window_name_keeps_save_disabled(self):
        page = self.browser.new_context().new_page()
        self.addCleanup(page.context.close)
        page.set_content(
            "<input id='name' value='Ada'><input id='email' value='ada@example.com'>"
            "<select id='role'><option value='Admin' selected>Admin</option></select>"
            "<button id='save' type='button' disabled>Save</button><script>"
            "var name=document.getElementById('name'); var email=document.getElementById('email');"
            "var role=document.getElementById('role'); var save=document.getElementById('save');"
            "function refresh(){ save.disabled=!(name.value && email.value && role.value); } refresh();"
            "</script>"
        )
        self.assertEqual(page.evaluate("typeof name"), "string")
        self.assertFalse(page.locator("#save").is_enabled())

    def test_a_second_miss_stops_before_save(self):
        page, state, episode, calls, outs = self._run(["Nope", "Nope"])
        self.assertFalse(episode["success"])
        self.assertEqual(state.plan["status"], "failed")
        self.assertEqual(state.plan["replans"], 1)
        self.assertEqual(calls, ["Fill name and email from row 3", "Fill name and email from row 3"])
        self.assertEqual(page.locator("#out").inner_text(), "")
        self.assertEqual(outs, [])


if __name__ == "__main__":
    unittest.main()
