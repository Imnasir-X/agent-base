"""The loop. It does not import Playwright, a model SDK, or the filesystem.

decide, observe, execute_turn, log, advance, planner, and reward are the only calls.
approver is None for ordinary actions. Targets marked requires_approval still pause.
"""
import time
import uuid

from actions import execute_turn
from logger import log_turn_end, log_turn_start
from perception import observe
from planner import next_subgoal
from reward import reward as score_episode
from state import advance


def approved(actions, approver) -> bool:
    """None allows ordinary actions. A callable gates the whole turn."""
    if approver is None:
        return True
    return bool(approver(actions))


def _risky(actions, obs) -> bool:
    flagged = {el["id"] for el in obs.elements if el.get("requires_approval")}
    for action in actions:
        if action.type == "approval_needed":
            return True
        if action.params.get("id") in flagged:
            return True
    return False


def must_pause(actions, obs, approver) -> bool:
    """Pause when the approver rejects the turn, or when a risky target has no approver."""
    if approver is None:
        return _risky(actions, obs)
    return not approver(actions)


def run_episode(page, state, decide, approver=None, max_steps: int = 5) -> dict:
    turns = 0
    latency_total = 0
    taken = []
    while state.step < max_steps:
        started = time.perf_counter()
        obs = observe(page)
        state.subgoal = next_subgoal(state, obs)
        actions = []
        error = None
        try:
            actions = list(decide(obs, state))
        except Exception as exc:
            error = "model:" + str(exc)[:300]
        turn_id = uuid.uuid4().hex[:12]
        log_turn_start(turn_id, state, obs, actions)
        results = []
        try:
            if error:
                pass
            elif must_pause(actions, obs, approver):
                state.pending_approval = [{"type": a.type, "params": dict(a.params)} for a in actions]
                error = "not_approved"
            else:
                state.pending_approval = None
                results = execute_turn(page, actions)
        except Exception as exc:
            error = str(exc)
        finally:
            latency = int((time.perf_counter() - started) * 1000)
            log_turn_end(turn_id, state.step, results, latency, len(actions), error)
        latency_total += latency
        turns += 1
        taken.extend({"type": a.type, "params": dict(a.params)} for a in actions)
        advance(state, actions, results)
        if error == "not_approved" or (error or "").startswith("model:"):
            break
        if _finished(actions, results):
            break
    episode = {"success": False, "num_turns": turns, "latency_ms": latency_total, "actions": taken}
    episode["reward"] = score_episode(episode)
    return episode


def _finished(actions, results) -> bool:
    for index, action in enumerate(actions):
        if action.type != "done":
            continue
        if index >= len(results) or results[index].success:
            return True
    return False
