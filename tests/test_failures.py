"""Failure injection and replay proof. Local fixtures only."""
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from actions import Action, execute_turn
from agent import run_episode
from eval_checks import run_check
from eval_runner import serve
from model_stub import decide
from perception import observe
from state import TaskState


class TestFailures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
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

    def test_stale_id_mid_batch(self):
        page = self.page("batch.html")
        obs = observe(page)
        remove = next(el for el in obs.elements if el["text"] == "Remove")
        stay = next(el for el in obs.elements if el["text"] == "Stay")
        results = execute_turn(page, [
            Action("click_element", {"id": remove["id"]}),
            Action("click_element", {"id": stay["id"]}),
        ])
        self.assertTrue(results[0].success, results[0].reason)
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].reason, "no_element_found")

    def test_navigation_mid_batch(self):
        page = self.page("batch.html")
        obs = observe(page)
        go = next(el for el in obs.elements if el["text"] == "Go")
        stay = next(el for el in obs.elements if el["text"] == "Stay")
        results = execute_turn(page, [
            Action("click_element", {"id": go["id"]}),
            Action("click_element", {"id": stay["id"]}),
        ])
        self.assertTrue(results[0].success, results[0].reason)
        self.assertFalse(results[1].success)
        self.assertIn(results[1].reason, ("no_element_found", "exception", "timeout"))

    def test_never_network_idle(self):
        page = self.page("stall.html")
        started = time.perf_counter()
        obs = observe(page)
        elapsed = time.perf_counter() - started
        self.assertGreaterEqual(elapsed, 5.0)
        self.assertLess(elapsed, 12.0)
        self.assertTrue(obs.raw_screenshot_path)
        self.assertTrue(obs.dom_hash)

    def test_checkout_pauses_until_approver_allows(self):
        page = self.page("checkout.html")
        log = config.LOG_DIR / "checkout_pause.jsonl"
        if log.exists():
            log.unlink()
        config.LOG_PATH = log
        config.STUB_MODE = "heuristic"
        state = TaskState("Click Checkout", "Click Checkout", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, None, 3)
        self.assertTrue(run_check(page, "approval_held", {"text": "checkout", "forbidden": "Order placed"}, state))
        self.assertEqual(page.locator("#out").inner_text(), "")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "replay.py"), str(log)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(any(item.get("skipped") == "not_approved" for item in report))
        allowed = self.page("checkout.html")
        state_ok = TaskState("Click Checkout", "Click Checkout", 0, [], [], None, "stub", None)
        run_episode(allowed, state_ok, decide, lambda actions: True, 3)
        self.assertEqual(allowed.locator("#out").inner_text(), "Order placed")

    def test_replay_cli_matches_log(self):
        httpd_port = self.port
        log = config.LOG_DIR / "replay_case.jsonl"
        if log.exists():
            log.unlink()
        config.LOG_PATH = log
        config.STUB_MODE = "heuristic"
        page = self.page("increment.html")
        state = TaskState("Click Increment", "Click Increment", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, None, 4)
        self.assertTrue(run_check(page, "text_visible", {"text": "Count is 1"}))
        page.context.close()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "replay.py"), str(log)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report)
        self.assertTrue(all(item["match"] for item in report))
        self.assertGreaterEqual(httpd_port, 1)

    def test_failed_captcha_replays(self):
        log = config.LOG_DIR / "captcha_decoy_replay.jsonl"
        if log.exists():
            log.unlink()
        config.LOG_PATH = log
        config.STUB_MODE = "heuristic"
        page = self.page("captcha_decoy.html")
        state = TaskState("Click Verify", "Click Verify", 0, [], [], None, "stub", None)
        run_episode(page, state, decide, None, 4)
        self.assertFalse(run_check(page, "text_visible", {"text": "Cleared"}))
        page.context.close()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "replay.py"), str(log)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report)
        self.assertTrue(all(item["match"] for item in report))


if __name__ == "__main__":
    unittest.main()
