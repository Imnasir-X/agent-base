"""Two JSONL lines per turn: intent before the action, outcome in a finally block."""
import json

import config


def _write(record: dict) -> None:
    config.LOG_PATH.parent.mkdir(exist_ok=True)
    with config.LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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
