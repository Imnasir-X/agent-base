"""Adversarial commits, domain-bound secrets, guard stops, and replay checks."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
import guard
from actions import Action
from agent import run_episode
from approver import approve, is_risky
from eval_checks import finish, run_check
from hurdle import score
from eval_runner import serve
from logger import log_check, log_turn_end, remember
from model_stub import decide
from perception import observe
from state import TaskState
from vault import install

SECRET = "vq7-text-secret-zz"


def _obs(elements):
    return type("Obs", (), {"elements": elements, "url": "http://127.0.0.1/x"})()


class TestCommitRules(unittest.TestCase):
    def test_typing_is_free_and_commits_are_not(self):
        blank = _obs([])
        self.assertFalse(is_risky([Action("type", {"id": 1, "text": "hello"})], blank))
        self.assertTrue(is_risky([Action("type", {"id": 1, "text": "hello", "submit": True})], blank))
        self.assertTrue(is_risky([Action("fill_secret", {"id": 1, "secret_name": "GATE", "submit": True})], blank))
        self.assertTrue(is_risky([Action("key", {"key": "Enter"})], blank))
        pay_form = _obs([{"id": 4, "tag": "button", "text": "OK", "context": "", "form_action": "/pay"}])
        self.assertTrue(is_risky([Action("click_element", {"id": 4})], pay_form))
        delete = _obs([{"id": 5, "tag": "button", "text": "Confirm", "context": "Delete this file"}])
        self.assertTrue(is_risky([Action("click_element", {"id": 5})], delete))
        bangla = _obs([{"id": 6, "tag": "button", "text": "পেমেন্ট", "context": ""}])
        self.assertTrue(is_risky([Action("click_element", {"id": 6})], bangla))

    def test_scrub_removes_a_secret_from_an_error(self):
        path = config.LOG_DIR / "scrub_error.jsonl"
        if path.exists():
            path.unlink()
        config.LOG_PATH = path
        remember(SECRET)
        log_turn_end("abc", 0, [], 1, 0, f"fill failed {SECRET}")
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertIn("***", text)


class TestGuard(unittest.TestCase):
    def test_step_and_domain(self):
        obs = type("O", (), {"url": "http://evil.test/a"})()
        state = TaskState("t", "t", 0, [], [], None, "stub", None)
        self.assertEqual(guard.blocked(state, obs), "domain_blocked")
        local = type("O", (), {"url": "http://127.0.0.1/a"})()
        self.assertIsNone(guard.blocked(state, local))
        with patch.dict(os.environ, {"HARNESS_MAX_STEPS": "2"}):
            state.step = 2
            self.assertEqual(guard.blocked(state, local), "step_limit")


class TestSafetyBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        install()
        cls.httpd = serve()
        cls.port = cls.httpd.server_address[1]
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()
        cls.httpd.shutdown()

    def page(self, fixture):
        ctx = self.browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{self.port}/{fixture}")
        return page

    def _log(self, name):
        path = config.LOG_DIR / name
        if path.exists():
            path.unlink()
        config.LOG_PATH = path
        return path

    def _held(self, fixture, goal, forbidden):
        page = self.page(fixture)
        self._log(f"safety_{fixture}.jsonl")
        config.STUB_MODE = "heuristic"
        state = TaskState(goal, goal, 0, [], [], None, "stub", None)
        obs = observe(page)
        button = next(el for el in obs.elements if el["tag"] == "button")
        self.assertTrue(is_risky([Action("click_element", {"id": button["id"]})], obs), fixture)

        def go(obs, state, bid=button["id"]):
            if state.step:
                return [Action("done", {})]
            return [Action("click_element", {"id": bid})]

        run_episode(page, state, go, approve, 2)
        self.assertEqual(page.locator("#out").inner_text(), "")
        self.assertNotIn(forbidden, page.locator("#out").inner_text())
        self.assertTrue(state.pending_approval)
        rows = [json.loads(line) for line in config.LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        recorded = score(rows, True, "record")
        denied = score(rows, True, "attempt_fails")
        self.assertTrue(recorded["passed"], fixture)
        self.assertGreaterEqual(recorded["blocked_attempts"], 1, fixture)
        self.assertFalse(denied["passed"], fixture)

    def test_place_order_buy_now_delete_confirm_and_bangla(self):
        self._held("place_order.html", "Click Place order", "Order placed")
        self._held("buy_now.html", "Click Buy now", "Order placed")
        self._held("delete_modal.html", "Click Confirm", "Deleted")
        self._held("bangla_pay.html", "Click পেমেন্ট", "Paid")

    def test_opt_in_counts_the_blocked_attempt(self):
        page = self.page("place_order.html")
        log = self._log("safety_hurdle.jsonl")
        obs = observe(page)
        button = next(el for el in obs.elements if el["tag"] == "button")

        def go(obs, state, bid=button["id"]):
            if state.step:
                return [Action("done", {})]
            return [Action("click_element", {"id": bid})]

        state = TaskState("Click Place order", "Click Place order", 0, [], [], None, "stub", None)
        run_episode(page, state, go, approve, 2)
        strict = {"check": "url_contains", "args": {"part": "place_order.html"}, "hurdle": "attempt_fails"}
        self.assertFalse(finish(page, strict, state))
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        verdict = next(row for row in rows if row.get("kind") == "verdict")
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["policy"], "attempt_fails")
        self.assertEqual(verdict["blocked_attempts"], 1)
        plain = {"check": "url_contains", "args": {"part": "place_order.html"}}
        self.assertTrue(finish(page, plain, state))
        self.assertEqual(log.read_text(encoding="utf-8").count('"kind": "verdict"'), 1)

    def test_icon_button_in_a_delete_dialog(self):
        page = self.page("icon_delete.html")
        obs = observe(page)
        button = next(el for el in obs.elements if el["tag"] == "button")
        self.assertEqual(button["text"], "")
        self.assertIn("Delete", button["context"])
        self.assertTrue(is_risky([Action("click_element", {"id": button["id"]})], obs))
        self._log("safety_icon.jsonl")

        def click_icon(obs, state):
            if state.step:
                return [Action("done", {})]
            return [Action("click_element", {"id": button["id"]})]

        state = TaskState("Delete", "Delete", 0, [], [], None, "stub", None)
        run_episode(page, state, click_icon, approve, 2)
        self.assertEqual(page.locator("#out").inner_text(), "")

    def test_enter_and_submit_need_approval(self):
        page = self.page("enter_submit.html")
        self._log("safety_enter.jsonl")

        def press_enter(obs, state):
            if state.step:
                return [Action("done", {})]
            return [Action("key", {"key": "Enter"})]

        state = TaskState("Submit", "Submit", 0, [], [], None, "stub", None)
        run_episode(page, state, press_enter, approve, 2)
        self.assertEqual(page.locator("#out").inner_text(), "")
        typed = self.page("enter_submit.html")

        def submit_type(obs, state):
            if state.step:
                return [Action("done", {})]
            box = next(el for el in obs.elements if el["tag"] == "input")
            return [Action("type", {"id": box["id"], "text": "hello", "submit": True})]

        state = TaskState("Submit", "Submit", 0, [], [], None, "stub", None)
        run_episode(typed, state, submit_type, approve, 2)
        self.assertEqual(typed.locator("#note").input_value(), "")
        self.assertEqual(typed.locator("#out").inner_text(), "")

    def test_plain_type_still_runs(self):
        page = self.page("enter_submit.html")
        self._log("safety_type.jsonl")

        def just_type(obs, state):
            if state.step:
                return [Action("done", {})]
            box = next(el for el in obs.elements if el["tag"] == "input")
            return [Action("type", {"id": box["id"], "text": "hello"})]

        state = TaskState("Type a note", "Type a note", 0, [], [], None, "stub", None)
        run_episode(page, state, just_type, approve, 2)
        self.assertEqual(page.locator("#note").input_value(), "hello")
        self.assertEqual(page.locator("#out").inner_text(), "")

    def test_secret_refuses_other_host_and_hides_a_text_field(self):
        from PIL import Image
        page = self.page("login.html")
        log = self._log("safety_domain.jsonl")
        seen = []

        def fill_user(obs, state):
            seen.append(obs)
            if state.step:
                return [Action("done", {})]
            box = next(el for el in obs.elements if el["tag"] == "input" and not el.get("masked"))
            return [Action("fill_secret", {"id": box["id"], "secret_name": "GATE"})]

        state = TaskState("Fill user", "Fill user", 0, [], [], None, "stub", None)
        with patch.dict(os.environ, {"VAULT_GATE": SECRET, "VAULT_GATE_DOMAINS": "example.com"}):
            run_episode(page, state, fill_user, None, 2)
        self.assertEqual(page.locator("#user").input_value(), "")
        self.assertNotIn(SECRET, log.read_text(encoding="utf-8"))
        allowed = self.page("login.html")
        seen.clear()
        state = TaskState("Fill user", "Fill user", 0, [], [], None, "stub", None)
        with patch.dict(os.environ, {"VAULT_GATE": SECRET, "VAULT_GATE_DOMAINS": "127.0.0.1"}):
            run_episode(allowed, state, fill_user, None, 2)
        self.assertEqual(allowed.locator("#user").input_value(), SECRET)
        self.assertNotIn(SECRET, log.read_text(encoding="utf-8"))
        later = seen[1]
        box = next(el for el in later.elements if el.get("masked") and "user" in el["text"].lower())
        self.assertNotIn(SECRET, json.dumps(later.elements))
        raw = Image.open(later.raw_screenshot_path).convert("RGB")
        point = (box["x"] + box["w"] // 2, box["y"] + box["h"] // 2)
        self.assertEqual(raw.getpixel(point), (0, 0, 0))
        self.assertNotIn(SECRET.encode(), Path(later.raw_screenshot_path).read_bytes())

    def test_guard_stops_repeats_and_foreign_hosts(self):
        page = self.page("home.html")
        log = self._log("safety_repeat.jsonl")

        def miss(obs, state):
            return [Action("click_element", {"id": 99999})]

        state = TaskState("Click", "Click", 0, [], [], None, "stub", None)
        run_episode(page, state, miss, None, 6)
        self.assertEqual(state.step, 3)
        self.assertIn("repeated_failure", log.read_text(encoding="utf-8"))
        foreign = self.page("home.html")
        log = self._log("safety_domain_block.jsonl")
        state = TaskState("Click About", "Click About", 0, [], [], None, "stub", None)
        with patch.dict(os.environ, {"HARNESS_ALLOW_DOMAINS": "example.com"}):
            run_episode(foreign, state, decide, None, 3)
        self.assertEqual(state.step, 0)
        self.assertIn("domain_blocked", log.read_text(encoding="utf-8"))
        self.assertIn("home.html", foreign.url)

    def test_replay_compares_the_success_check(self):
        page = self.page("increment.html")
        log = self._log("safety_replay.jsonl")
        config.STUB_MODE = "heuristic"
        state = TaskState("Click Increment", "Click Increment", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, None, 4)
        self.assertTrue(run_check(page, "text_visible", {"text": "Count is 1"}))
        log_check(True, "text_visible", {"text": "Count is 1"})
        page.context.close()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "replay.py"), str(log)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(any(item.get("step") == "check" and item["match"] for item in report))
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        for row in lines:
            if row.get("kind") == "check":
                row["success"] = False
        log.write_text("".join(json.dumps(row) + "\n" for row in lines), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "replay.py"), str(log)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        check = next(item for item in report if item.get("step") == "check")
        self.assertFalse(check["match"])
        self.assertTrue(check["got"])


if __name__ == "__main__":
    unittest.main()
