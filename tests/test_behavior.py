"""The pure core must keep matching core_cases.json."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import behavior


class TestCoreContract(unittest.TestCase):
    def test_python_matches_the_contract(self):
        bad = behavior.compare()
        self.assertEqual(bad, [], bad)


if __name__ == "__main__":
    unittest.main()
