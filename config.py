"""Paths, model switch, and feature flags. Set before a run, not mid-turn.

LOG_PATH is assigned by main or eval_runner before an episode. The only
mutable global that changes during a run is actions.COMPOSITES, and that
registry is documented in actions.py.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "eval_fixtures"
LOG_DIR = ROOT / "logs"
RUN_DIR = ROOT / "runs"
LOG_DIR.mkdir(exist_ok=True)
RUN_DIR.mkdir(exist_ok=True)

# main.py reads these. agent.py does not choose a model.
MODEL = os.environ.get("HARNESS_MODEL", "stub")  # "stub" | "real"
STUB_MODE = os.environ.get("HARNESS_STUB_MODE", "heuristic")  # "heuristic" | "random" | "done"

SETTLE_MS = 500
MAX_STEPS = 5
POS_TOLERANCE = 8
PIXEL_DIFF_THRESHOLD = 0.01
EVAL_RUNS = 3
VIEWPORT = {"width": 1100, "height": 800}

# SpaceXAI via the xAI API. Image understanding sample uses grok-4.7.
# https://docs.x.ai/developers/model-capabilities/images/understanding
XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.7")

LOG_PATH = LOG_DIR / "turns.jsonl"
