"""TaskState and the one function that moves it forward."""
from dataclasses import dataclass

from actions import Action, ActionResult
from planner import next_subgoal


@dataclass
class TaskState:
    task: str
    subgoal: str
    step: int
    completed: list
    failures: list
    pending_approval: list | None
    model_name: str
    last_failure: dict | None
    plan: dict | None = None
    notes: dict | None = None


def advance(state: TaskState, actions: list[Action], results: list[ActionResult]) -> None:
    """Record results, keep last_failure, then ask the planner for the next subgoal."""
    padded = list(results)
    if len(padded) < len(actions):
        padded += [ActionResult(False, "exception")] * (len(actions) - len(padded))
    saw_failure = False
    for action, result in zip(actions, padded):
        record = {
            "type": action.type,
            "params": dict(action.params),
            "success": result.success,
            "reason": result.reason,
        }
        if result.success:
            state.completed.append(record)
        else:
            state.failures.append(record)
            state.last_failure = {
                "action": {"type": action.type, "params": dict(action.params)},
                "reason": result.reason,
            }
            saw_failure = True
    if padded and not saw_failure:
        state.last_failure = None
    state.step += 1
    state.subgoal = next_subgoal(state, None)
