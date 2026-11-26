"""Two JSONL lines per turn: intent before the action, outcome in a finally block.

remember() holds secret and OTP strings in memory. _write scrubs a copy, so
the live action params stay intact for the browser.
"""
import json

import config

_HELD: list[str] = []


def remember(text: str) -> None:
    text = str(text or "")
    if len(text) < 2 or text in _HELD:
        return
    _HELD.append(text)


def held() -> set[str]:
    return set(_HELD)


def scrub(value):
    if isinstance(value, str):
        for secret in sorted(_HELD, key=len, reverse=True):
            if secret in value:
                value = value.replace(secret, "***")
        return value
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def _write(record: dict) -> None:
    safe = scrub(json.loads(json.dumps(record)))
    config.LOG_PATH.parent.mkdir(exist_ok=True)
    with config.LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe, ensure_ascii=False) + "\n")


def log_turn_start(turn_id: str, state, observation, actions) -> None:
    _write({
        "kind": "intent",
        "turn_id": turn_id,
        "step": state.step,
        "task": state.task,
        "subgoal": state.subgoal,
        "observation": {
            "raw": observation.raw_screenshot_path,
            "som": observation.som_screenshot_path,
            "url": observation.url,
        },
        "actions": [{"type": action.type, "params": action.params} for action in actions],
        "model": state.model_name,
    })


def log_turn_end(turn_id: str, step: int, results, latency_ms: int,
                 num_actions: int, error: str | None = None) -> None:
    _write({
        "kind": "outcome",
        "turn_id": turn_id,
        "step": step,
        "results": [{"success": item.success, "reason": item.reason} for item in results],
        "num_actions": num_actions,
        "latency_ms": latency_ms,
        "error": error,
    })


def log_check(success: bool, name: str, args: dict | None = None) -> None:
    _write({"kind": "check", "success": bool(success), "check": name, "args": args or {}})


def log_verdict(passed: bool, policy: str, blocked: int) -> None:
    _write({
        "kind": "verdict",
        "passed": bool(passed),
        "policy": policy,
        "blocked_attempts": int(blocked),
    })
