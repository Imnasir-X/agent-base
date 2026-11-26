"""Saved session, secret vault, approver, and ask_user. Local fixtures only."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from actions import Action
from agent import run_episode
from approver import approve, is_risky
from ask_user import answer
from eval_checks import run_check
from eval_runner import serve
from login_once import login_once
from model_stub import decide
from PIL import Image
from state import TaskState
from vault import install, lookup

SECRET = "vq7-gate-secret-zz"


def _obs(elements):
    return type("Obs", (), {"elements": elements})()


class TestApproverUnit(unittest.TestCase):
    def test_risky_words_and_bare_confirm(self):
        checkout = _obs([{"id": 1, "text": "Checkout"}])
        confirm = _obs([{"id": 2, "text": "Confirm"}])
        order = _obs([{"id": 3, "text": "Confirm order"}])
        click = lambda eid: [Action("click_element", {"id": eid})]
        self.assertTrue(is_risky(click(1), checkout))
        self.assertFalse(is_risky(click(2), confirm))
        self.assertTrue(is_risky(click(3), order))
        self.assertTrue(is_risky([Action("click_element", {"text": "Submit order"})], _obs([])))
        self.assertFalse(approve(click(1), checkout, mode="eval"))
        self.assertTrue(approve(click(2), confirm, mode="eval"))

    def test_eval_does_not_read_stdin(self):
        checkout = _obs([{"id": 1, "text": "Pay now"}])
        with patch("builtins.input", side_effect=AssertionError("input called")):
            self.assertFalse(approve([Action("click_element", {"id": 1})], checkout, mode="eval"))
            with patch.dict(os.environ, {"HARNESS_APPROVER": "interactive"}):
                pass
        with patch("builtins.input", return_value="y"):
            self.assertTrue(approve([Action("click_element", {"id": 1})], checkout, mode="interactive"))
        with patch("builtins.input", return_value="n"):
            self.assertFalse(approve([Action("click_element", {"id": 1})], checkout, mode="interactive"))

    def test_lookup_env_and_file(self):
        path = config.ROOT / "secrets.json"
        self.assertFalse(path.exists())
        path.write_text(
            '{"FILEKEY": {"value": "from-file-only", "domains": ["files.test"]}}',
            encoding="utf-8",
        )
        try:
            with patch.dict(os.environ, {"VAULT_GATE": SECRET, "VAULT_GATE_DOMAINS": "127.0.0.1"}):
                self.assertEqual(lookup("GATE", "127.0.0.1"), SECRET)
                with self.assertRaises(KeyError):
                    lookup("GATE", "evil.test")
            self.assertEqual(lookup("FILEKEY", "files.test"), "from-file-only")
            with self.assertRaises(KeyError):
                lookup("FILEKEY", "127.0.0.1")
        finally:
            path.unlink(missing_ok=True)


class TestSession(unittest.TestCase):
    def test_saved_login_needs_no_login_actions(self):
        old = config.SESSION_DIR
        previous = config.STUB_MODE
        config.STUB_MODE = "heuristic"
        httpd = serve()
        port = httpd.server_address[1]
        log = config.LOG_DIR / "phase_session.jsonl"
        if log.exists():
            log.unlink()
        config.LOG_PATH = log
        tmp = tempfile.TemporaryDirectory()
        config.SESSION_DIR = Path(tmp.name)
        try:
            url = f"http://127.0.0.1:{port}/login.html"

            def filler(page):
                page.locator("#user").fill("ada")
                page.locator("#pw").fill("hand-login")
                page.locator("#go").click()
                page.wait_for_url("**/inbox.html")

            login_once(url, filler=filler)
            from playwright.sync_api import sync_playwright
            from session import open_context
            with sync_playwright() as playwright:
                context = open_context(playwright, True)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(f"http://127.0.0.1:{port}/inbox.html")
                self.assertEqual(page.locator("#gate").inner_text(), "Welcome")
                state = TaskState("Click Open message", "Click Open message", 0, [], [], None, "stub", None)
                run_episode(page, state, decide, None, 3)
                self.assertIn("opened.html", page.url)
                context.close()
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            actions = [item for row in rows if row["kind"] == "intent" for item in row["actions"]]
            self.assertTrue(actions)
            self.assertTrue(all(item["type"] not in ("type", "fill_secret") for item in actions))
            blob = json.dumps(actions).lower()
            self.assertNotIn("log in", blob)
            self.assertNotIn("password", blob)
        finally:
            config.SESSION_DIR = old
            config.STUB_MODE = previous
            httpd.shutdown()
            tmp.cleanup()


class TestBrowserPhaseA(unittest.TestCase):
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

    def test_fill_secret_stays_out_of_logs_and_shots(self):
        page = self.page("login.html")
        log = self._log("phase_vault.jsonl")
        seen = []
        started = page.evaluate("() => Date.now()")

        def scripted(obs, state):
            seen.append(obs)
            if state.step == 0:
                box = next(el for el in obs.elements if el.get("masked"))
                return [Action("fill_secret", {"id": box["id"], "secret_name": "GATE"})]
            return [Action("done", {})]

        state = TaskState("Fill the password", "Fill the password", 0, [], [], None, "stub", None)
        with patch.dict(os.environ, {"VAULT_GATE": SECRET, "VAULT_GATE_DOMAINS": "127.0.0.1"}):
            run_episode(page, state, scripted, None, 2)
        self.assertEqual(page.locator("#pw").input_value(), SECRET)
        self.assertNotIn(SECRET, log.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(seen), 2)
        for obs in seen:
            blob = json.dumps(obs.elements)
            self.assertNotIn(SECRET, blob)
            self.assertTrue(any(el.get("masked") for el in obs.elements))
        later = seen[1]
        box = next(el for el in later.elements if el.get("masked"))
        som = Image.open(later.som_screenshot_path).convert("RGB")
        raw = Image.open(later.raw_screenshot_path).convert("RGB")
        point = (box["x"] + box["w"] // 2, box["y"] + box["h"] // 2)
        self.assertEqual(som.getpixel(point), (0, 0, 0))
        self.assertEqual(raw.getpixel(point), (0, 0, 0))
        self._secret_absent(started)

    def _secret_absent(self, started_ms):
        needle = SECRET.encode()
        for folder in (config.LOG_DIR, config.RUN_DIR):
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue
                if folder == config.RUN_DIR and path.stat().st_mtime * 1000 < started_ms - 5000:
                    continue
                data = path.read_bytes()
                self.assertNotIn(needle, data, str(path))

    def test_eval_denies_checkout_and_grant_places_it(self):
        page = self.page("checkout.html")
        self._log("phase_deny.jsonl")
        config.STUB_MODE = "heuristic"
        state = TaskState("Click Checkout", "Click Checkout", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, approve, 4)
        self.assertGreaterEqual(state.step, 2)
        self.assertEqual(page.locator("#out").inner_text(), "")
        self.assertTrue(run_check(page, "approval_held", {"text": "checkout", "forbidden": "Order placed"}, state))
        allowed = self.page("checkout.html")
        state_ok = TaskState("Click Checkout", "Click Checkout", 0, [], [], None, "stub", None)
        run_episode(allowed, state_ok, decide, lambda actions, obs: True, 3)
        self.assertEqual(allowed.locator("#out").inner_text(), "Order placed")

    def test_bare_confirm_still_runs(self):
        page = self.page("modal_ok.html")
        self._log("phase_confirm.jsonl")
        config.STUB_MODE = "heuristic"
        state = TaskState("Click Open then click Confirm", "Click Open then click Confirm", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, approve, 4)
        self.assertTrue(run_check(page, "text_visible", {"text": "Confirmed"}))

    def test_ask_user_answer_finishes_and_skips_the_intent_log(self):
        page = self.page("code_gate.html")
        log = self._log("phase_ask.jsonl")
        reply = config.LOG_DIR / "phase_answer.txt"
        reply.write_text("4419\n", encoding="utf-8")

        def scripted(obs, state):
            if state.step == 0:
                return [Action("ask_user", {"question": "What is the code?"})]
            code = ""
            for rec in state.completed:
                if rec.get("type") == "ask_user":
                    code = (rec.get("params") or {}).get("answer", "")
            if state.step == 1:
                box = next(el for el in obs.elements if el["tag"] == "input")
                return [Action("type", {"id": box["id"], "text": code})]
            button = next(el for el in obs.elements if "Check" in el["text"])
            return [Action("click_element", {"id": button["id"], "text": button["text"]})]

        state = TaskState("Enter the code", "Enter the code", 0, [], [], None, "stub", None)
        with patch.dict(os.environ, {"HARNESS_ANSWER_FILE": str(reply)}):
            episode = run_episode(page, state, scripted, None, 4, answer)
        self.assertEqual(page.locator("#out").inner_text(), "Unlocked")
        self.assertIn("What is the code?", (config.LOG_DIR / "question.txt").read_text(encoding="utf-8"))
        self.assertNotIn("4419", log.read_text(encoding="utf-8"))
        self.assertNotIn("4419", json.dumps(episode["actions"]))
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        first = next(row for row in rows if row["kind"] == "intent")
        self.assertEqual(first["actions"][0]["type"], "ask_user")
        reply.unlink(missing_ok=True)

    def test_ask_user_without_answerer_stops(self):
        page = self.page("code_gate.html")
        log = self._log("phase_wait.jsonl")

        def asking(obs, state):
            return [Action("ask_user", {"question": "Code?"})]

        state = TaskState("Enter the code", "Enter the code", 0, [], [], None, "stub", None)
        run_episode(page, state, asking, None, 4, None)
        self.assertEqual(state.step, 1)
        self.assertTrue(state.pending_approval)
        outcome = next(json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if '"outcome"' in line)
        self.assertEqual(outcome["error"], "waiting_user")


if __name__ == "__main__":
    unittest.main()
