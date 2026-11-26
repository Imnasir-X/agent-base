"""Pure-core behavioral contract.

The browser and the model stay outside this file. Each case in
core_cases.json is one input and one expected result. Python is the
reference. A Rust port of these operations must return the same results.
Changing an expected value is a behavior change: record it in CHANGELOG.md.
"""
import json
import os
import sys
from pathlib import Path

import guard
import logger
from actions import Action, ActionResult
from hurdle import score as hurdle_score
from approver import approve, is_risky
from planner import next_subgoal
from reward import reward
from state import TaskState, advance
from vault import lookup

CASES = Path(__file__).resolve().parent / "core_cases.json"


def _state(data):
    data = data or {}
    state = TaskState(
        data.get("task", ""), data.get("subgoal", ""), int(data.get("step") or 0),
        list(data.get("completed") or []), list(data.get("failures") or []),
        data.get("pending_approval"), data.get("model_name", "oracle"), data.get("last_failure"),
    )
    if "plan" in data:
        state.plan = data["plan"]
    if "notes" in data:
        state.notes = dict(data["notes"])
    return state


def _obs(case):
    return type("Obs", (), {"url": case.get("url") or "", "elements": case.get("elements") or []})()


def _actions(items):
    return [Action(item["type"], dict(item.get("params") or {})) for item in items or []]


def _snap(state):
    return {
        "step": state.step, "subgoal": state.subgoal, "completed": state.completed,
        "failures": state.failures, "last_failure": state.last_failure,
    }


def run_one(case):
    op = case["op"]
    if op == "guard.blocked":
        return guard.blocked(_state(case.get("state")), _obs(case))
    if op == "approver.is_risky":
        return is_risky(_actions(case.get("actions")), _obs(case))
    if op == "approver.approve":
        return approve(_actions(case.get("actions")), _obs(case), case.get("mode") or "eval")
    if op == "planner.next_subgoal":
        obs = _obs(case) if case.get("has_observation") else None
        return next_subgoal(_state(case.get("state")), obs)
    if op == "state.advance":
        state = _state(case.get("state"))
        results = [ActionResult(bool(item.get("success")), item.get("reason") or "") for item in case.get("results") or []]
        advance(state, _actions(case.get("actions")), results)
        return _snap(state)
    if op == "reward.score":
        return reward(case["episode"])
    if op == "vault.lookup":
        try:
            return {"ok": lookup(case["name"], case["host"])}
        except KeyError:
            return {"error": "KeyError"}
    if op == "logger.scrub":
        logger._HELD.clear()
        for text in case.get("remember") or []:
            logger.remember(text)
        return logger.scrub(case.get("value"))
    if op == "hurdle.score":
        return hurdle_score(case.get("rows") or [], bool(case.get("code_ok")), case.get("policy") or "record")
    if op == "plan.apply":
        from plan_report import apply_case
        return apply_case(case)
    raise KeyError(op)


def compare(path=None):
    """Return mismatches. Empty means the Python core still matches the contract."""
    data = json.loads(Path(path or CASES).read_text(encoding="utf-8"))
    bad = []
    held = list(logger._HELD)
    for case in data["cases"]:
        keys = case.get("env") or {}
        old = {key: os.environ.get(key) for key in keys}
        try:
            os.environ.update(keys)
            got = run_one(case)
            if got != case["expect"]:
                bad.append({"id": case["id"], "got": got, "expect": case["expect"]})
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            logger._HELD[:] = held
    return bad


def main():
    bad = compare()
    print(json.dumps({"ok": not bad, "mismatches": bad}, indent=2, ensure_ascii=False))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
