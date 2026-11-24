"""Do-nothing must score 0. Random must score near 0. Heuristic stays in the 50-70% band."""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from eval_runner import run_eval


class TestControls(unittest.TestCase):
    def tearDown(self):
        config.MODEL = "stub"
        config.STUB_MODE = "heuristic"

    def test_do_nothing_fails_every_task(self):
        config.STUB_MODE = "done"
        stats = run_eval(1)
        passed = [row["name"] for row in stats["tasks"] if row["successes"]]
        print("done", stats["success_rate"], passed)
        self.assertEqual(passed, [])
        self.assertEqual(stats["success_rate"]["mean"], 0.0)

    def test_random_scores_near_zero(self):
        random.seed(0)
        config.STUB_MODE = "random"
        stats = run_eval(1)
        passed = [row["name"] for row in stats["tasks"] if row["successes"]]
        print("random", stats["success_rate"], passed)
        self.assertLessEqual(stats["success_rate"]["mean"], 0.1, passed)

    def test_heuristic_scores_in_band(self):
        config.STUB_MODE = "heuristic"
        stats = run_eval(1)
        rate = stats["success_rate"]["mean"]
        detail = [(row["name"], row["successes"]) for row in stats["tasks"]]
        print("heuristic", stats["success_rate"], detail)
        self.assertGreaterEqual(rate, 0.5, detail)
        self.assertLessEqual(rate, 0.7, detail)


if __name__ == "__main__":
    unittest.main()
