"""Re-execute a turn log on a fresh local fixture.

Intent lines supply the action list. Outcome lines supply the expected results.
A not_approved outcome is not executed again. Exit code 1 means a step diverged.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import config
from actions import Action, execute_turn
from eval_checks import run_check
from eval_runner import serve
from perception import observe
from state import TaskState


def load_turns(path: Path) -> list[tuple[dict, dict | None]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    intents = [row for row in rows if row.get("kind") == "intent"]
    outcomes = {row["turn_id"]: row for row in rows if row.get("kind") == "outcome"}
    intents.sort(key=lambda row: row["step"])
    return [(row, outcomes.get(row["turn_id"])) for row in intents]


def replay(path: Path) -> list[dict]:
    turns = load_turns(path)
    if not turns:
        raise SystemExit(f"no turns in {path}")
    start = urlparse(turns[0][0]["observation"]["url"])
    target = start.path + (("?" + start.query) if start.query else "")
    httpd = serve()
    port = httpd.server_address[1]
    report = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1)
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{port}{target}")
        for intent, outcome in turns:
            if outcome and outcome.get("error") == "not_approved":
                report.append({"step": intent["step"], "match": True, "skipped": "not_approved"})
                continue
            observe(page)
            actions = [Action(item["type"], dict(item.get("params") or {})) for item in intent["actions"]]
            results = execute_turn(page, actions)
            logged = (outcome or {}).get("results") or []
            got = [item.success for item in results]
            expected = [item["success"] for item in logged]
            report.append({
                "step": intent["step"],
                "match": got == expected,
                "got": [item.reason for item in results],
                "url": page.url,
            })
        report.extend(_check_report(path, page, turns))
        browser.close()
    httpd.shutdown()
    return report


def _check_report(path: Path, page, turns) -> list[dict]:
    row = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("kind") == "check":
            row = item
    if row is None:
        return []
    pending = None
    for intent, outcome in turns:
        if outcome and outcome.get("error") == "not_approved":
            pending = intent.get("actions") or []
    state = TaskState("replay", "replay", 0, [], [], pending, "replay", None)
    got = bool(run_check(page, row["check"], row.get("args") or {}, state))
    return [{"step": "check", "match": got == bool(row["success"]), "got": got}]


def main():
    parser = argparse.ArgumentParser(description="Replay a JSONL turn log")
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    report = replay(args.log)
    print(json.dumps(report, indent=2))
    if not report or any(not item["match"] for item in report):
        sys.exit(1)


if __name__ == "__main__":
    main()
