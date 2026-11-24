"""Milestone checks for the local harness. No live sites."""
import ast
import inspect
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from actions import Action, ActionResult, execute_turn
from agent import approved, run_episode
from eval_checks import run_check
from model_real import parse_actions
from model_stub import _TYPE, _math_pair, decide
from perception import observe
from PIL import Image
from reward import reward
from state import TaskState, advance


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


class TestShape(unittest.TestCase):
    def test_modules_import_and_hints(self):
        modules = [
            "agent", "actions", "perception", "state", "logger", "reward",
            "model_stub", "model_real", "planner", "eval_checks", "eval_runner", "main",
        ]
        for name in modules:
            __import__(name)
        self.assertIsNot(inspect.signature(observe).return_annotation, inspect.Signature.empty)
        self.assertIsNot(inspect.signature(decide).return_annotation, inspect.Signature.empty)
        self.assertIsNot(inspect.signature(execute_turn).return_annotation, inspect.Signature.empty)

    def test_agent_has_no_playwright_or_sdk(self):
        tree = ast.parse((ROOT / "agent.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("playwright", node.module or "")
                self.assertNotIn("openai", node.module or "")
            if isinstance(node, ast.Import):
                names = " ".join(alias.name for alias in node.names)
                self.assertNotIn("playwright", names)
                self.assertNotIn("openai", names)

    def test_files_stay_short(self):
        for name in [
            "config.py", "main.py", "agent.py", "perception.py", "actions.py", "state.py",
            "planner.py", "logger.py", "reward.py", "model_stub.py", "model_real.py", "model_gemini.py",
            "eval_checks.py", "eval_runner.py", "replay.py",
        ]:
            self.assertLessEqual(_lines(ROOT / name), 150, name)

    def test_type_parser_and_reward(self):
        goal = "Type 'Ada' into Name, type 'ada@example.com' into Email, and submit"
        self.assertEqual(_TYPE.findall(goal), [("Ada", "Name"), ("ada@example.com", "Email")])
        puzzle = type("S", (), {"task": "Solve 3 + 4 and type the answer into Answer"})()
        self.assertEqual(_math_pair(puzzle), [("7", "Answer")])
        self.assertAlmostEqual(reward({"success": True, "num_turns": 2, "latency_ms": 2000, "actions": []}), 0.985)

    def test_parse_actions_and_approver(self):
        payload = {"output_text": json.dumps({"actions": [{"type": "done", "params": {}}]})}
        self.assertEqual(parse_actions(payload)[0].type, "done")
        from model_gemini import _parse
        gemini = {"candidates": [{"content": {"parts": [{"text": "{\"actions\":[{\"type\":\"done\",\"params\":{}}]}"}]}}]}
        self.assertEqual(_parse(gemini)[0].type, "done")
        bare = {"candidates": [{"content": {"parts": [{"text": "[{\"type\":\"click_element\",\"params\":{\"id\":2}}]"}]}}]}
        self.assertEqual(_parse(bare)[0].params["id"], 2)
        single = {"candidates": [{"content": {"parts": [{"text": "{\"action\":{\"type\":\"click_element\",\"params\":{\"id\":19}}}"}]}}]}
        self.assertEqual(_parse(single)[0].params["id"], 19)
        self.assertTrue(approved([Action("done", {})], None))
        self.assertFalse(approved([Action("click_element", {"id": 1})], lambda actions: False))

    def test_twenty_tasks(self):
        tasks = json.loads((ROOT / "eval_tasks.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(tasks), 20)


class TestBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from eval_runner import serve
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
        page.goto(self._url(fixture))
        return page

    def _url(self, fixture):
        return f"http://127.0.0.1:{self.port}/{fixture}"

    def _log(self, name):
        path = config.LOG_DIR / name
        if path.exists():
            path.unlink()
        config.LOG_PATH = path
        return path

    def test_m0_screenshot(self):
        subprocess.run([sys.executable, str(ROOT / "main.py"), "--m0"], check=True, cwd=ROOT)
        image = Image.open(ROOT / "runs" / "m0.png").convert("RGB")
        self.assertEqual(image.getpixel((2, 2)), (18, 52, 86))
        colors = image.getcolors(maxcolors=200000)
        self.assertTrue(any(item[1][0] > 240 and item[1][1] > 240 and item[1][2] > 240 for item in colors))

    def test_m2_click_and_type(self):
        page = self.page("home.html")
        obs = observe(page)
        about = next(el for el in obs.elements if "About" in el["text"])
        result = execute_turn(page, [Action("click_element", {"id": about["id"]})])[0]
        self.assertTrue(result.success, result.reason)
        self.assertIn("about.html", page.url)
        page.goto(self._url("search.html"))
        obs = observe(page)
        box = next(el for el in obs.elements if el["tag"] == "input")
        typed = execute_turn(page, [Action("type", {"id": box["id"], "text": "hello"})])[0]
        self.assertTrue(typed.success, typed.reason)
        self.assertEqual(page.locator("#search").input_value(), "hello")

    def test_m3_som_and_stable_hash(self):
        page = self.page("home.html")
        first = observe(page)
        second = observe(page)
        self.assertEqual(first.dom_hash, second.dom_hash)
        raw = Image.open(first.raw_screenshot_path).convert("RGB")
        som = Image.open(first.som_screenshot_path).convert("RGB")
        self.assertGreater(_red(som), _red(raw) + 20)
        self.assertGreaterEqual(len(first.elements), 4)

    def test_m4_three_lines_and_injected_failure(self):
        page = self.page("counter.html")
        path = self._log("m4.jsonl")

        def always_click(obs, state):
            return [Action("click_element", {"id": 1})]

        state = TaskState("Click Increment", "Click Increment", 0, [], [], None, "stub", None)
        run_episode(page, state, always_click, None, 3)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        intents = [row for row in rows if row["kind"] == "intent"]
        outcomes = [row for row in rows if row["kind"] == "outcome"]
        self.assertEqual(len(intents), 3)
        self.assertEqual([row["turn_id"] for row in intents], [row["turn_id"] for row in outcomes])
        for row in intents:
            for key in ("step", "task", "subgoal", "observation", "actions", "model"):
                self.assertIn(key, row)
        page.goto(self._url("counter.html"))
        path = self._log("m4b.jsonl")

        def bad_then_done(obs, state):
            if state.step == 0:
                return [Action("click_element", {"id": 99999})]
            return [Action("done", {})]

        state = TaskState("Click Increment", "Click Increment", 0, [], [], None, "stub", None)
        run_episode(page, state, bad_then_done, None, 1)
        self.assertEqual(state.last_failure["reason"], "no_element_found")

    def test_m5_random_stub_five_turns(self):
        page = self.page("home.html")
        path = self._log("m5.jsonl")
        config.STUB_MODE = "random"
        random.seed(1)
        state = TaskState("Click About", "Click About", 0, [], [], None, "stub", None)
        try:
            run_episode(page, state, decide, None, 5)
        finally:
            config.STUB_MODE = "heuristic"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(row["kind"] == "outcome" for row in rows), 5)
        self.assertTrue(any(row["kind"] == "outcome" and any(item["success"] for item in row["results"]) for row in rows))

    def test_m6_missing_element_is_visible_to_stub(self):
        page = self.page("home.html")
        obs = observe(page)
        result = execute_turn(page, [Action("click_element", {"id": 99999})])[0]
        self.assertEqual(result.reason, "no_element_found")
        state = TaskState("Click About", "Click About", 0, [], [], None, "stub", None)
        advance(state, [Action("click_element", {"id": obs.elements[0]["id"]})], [ActionResult(False, "no_element_found")])
        config.STUB_MODE = "random"
        random.seed(2)
        try:
            action = decide(obs, state)[0]
        finally:
            config.STUB_MODE = "heuristic"
        self.assertNotEqual(action.params.get("id"), obs.elements[0]["id"])

    def test_label_text_is_on_the_input(self):
        page = self.page("search.html")
        obs = observe(page)
        box = next(el for el in obs.elements if el["tag"] == "input")
        self.assertIn("search", box["text"].lower())

    def test_composite_and_approver_and_tall(self):
        page = self.page("home.html")
        result = execute_turn(page, [Action("composite", {"name": "noop", "params": {}})])[0]
        self.assertTrue(result.success, result.reason)
        path = self._log("approve.jsonl")
        state = TaskState("Click About", "Click About", 0, [], [], None, "stub", None)
        config.STUB_MODE = "heuristic"
        run_episode(page, state, decide, lambda actions: False, 2)
        self.assertIn("home.html", page.url)
        self.assertTrue(state.pending_approval)
        outcome = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
        self.assertEqual(outcome["error"], "not_approved")
        tall = self.page("tall.html")
        found = observe(tall)
        finish = next(el for el in found.elements if "Finish" in el["text"])
        clicked = execute_turn(tall, [Action("click_element", {"id": finish["id"]})])[0]
        self.assertTrue(clicked.success, clicked.reason)
        self.assertTrue(run_check(tall, "text_visible", {"text": "All done"}))


def _red(image: Image.Image) -> int:
    data = image.convert("RGB").tobytes()
    count = 0
    for index in range(0, len(data), 3):
        if data[index] > 200 and data[index + 1] < 80 and data[index + 2] < 80:
            count += 1
    return count


if __name__ == "__main__":
    unittest.main()
