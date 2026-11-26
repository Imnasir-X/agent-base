"""The loop. It does not import Playwright, a model SDK, or the filesystem.

decide, observe, execute_turn, log, advance, planner, and reward are the only calls.
A plan adds scripted actions and a per-subgoal check. approver is None for
ordinary actions. Targets marked requires_approval still pause.
"""
import time
import uuid

from actions import execute_turn
import guard
from logger import log_turn_end, log_turn_start, remember, scrub
from perception import observe
from plan_run import capture, executable, mark_url, scripted_actions, settle
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


def _allow(approver, actions, obs) -> bool:
    try:
        return bool(approver(actions, obs))
    except TypeError:
        return bool(approver(actions))


def must_pause(actions, obs, approver) -> bool:
    """Pause when the approver rejects the turn, or when a risky target has no approver."""
    if approver is None:
        return _risky(actions, obs)
    return not _allow(approver, actions, obs)


def _answer(actions, obs, answerer, state):
    from actions import ActionResult
    state.pending_approval = [{"type": a.type, "params": dict(a.params)} for a in actions]
    if answerer is None:
        return [], "waiting_user"
    reply = str(answerer(actions, obs))
    remember(reply)
    for action in actions:
        if action.type == "ask_user":
            action.params["answer"] = reply
    state.pending_approval = None
    return [ActionResult(True, "")], None


def run_episode(page, state, decide, approver=None, max_steps: int = 5, answerer=None) -> dict:
    turns = 0
    latency_total = 0
    taken = []
    while state.step < max_steps and state.step < guard.ceiling():
        started = time.perf_counter()
        obs = observe(page)
        stop = guard.blocked(state, obs)
        if stop:
            turn_id = uuid.uuid4().hex[:12]
            log_turn_start(turn_id, state, obs, [])
            log_turn_end(turn_id, state.step, [], int((time.perf_counter() - started) * 1000), 0, stop)
            break
        state.subgoal = next_subgoal(state, obs)
        if state.plan:
            mark_url(state, page)
        actions = []
        error = None
        scripted = scripted_actions(state) if state.plan else None
        try:
            proposed = scripted if scripted is not None else list(decide(obs, state))
            if state.plan:
                capture(state, proposed)
                actions = executable(state, proposed)
            else:
                actions = proposed
        except Exception as exc:
            error = "model:" + scrub(str(exc))[:300]
        turn_id = uuid.uuid4().hex[:12]
        log_turn_start(turn_id, state, obs, actions)
        results = []
        try:
            if error:
                pass
            elif any(action.type == "ask_user" for action in actions):
                results, error = _answer(actions, obs, answerer, state)
            elif must_pause(actions, obs, approver):
                state.pending_approval = [{"type": a.type, "params": dict(a.params)} for a in actions]
                error = "not_approved"
            else:
                results = execute_turn(page, actions)
        except Exception as exc:
            error = scrub(str(exc))
        finally:
            latency = int((time.perf_counter() - started) * 1000)
            log_turn_end(turn_id, state.step, results, latency, len(actions), error)
        latency_total += latency
        turns += 1
        taken.extend({"type": a.type, "params": dict(a.params)} for a in actions)
        advance(state, actions, results)
        if (error or "").startswith("model:") or error == "waiting_user":
            break
        if state.plan:
            if settle(state, page):
                break
        elif _finished(actions, results):
            break
    planned = bool(state.plan and state.plan.get("status") == "done")
    episode = {"success": planned, "num_turns": turns, "latency_ms": latency_total, "actions": scrub(taken)}
    if state.plan:
        episode["subgoals"] = list(state.plan.get("results") or [])
        episode["replans"] = state.plan.get("replans") or 0
    episode["reward"] = score_episode(episode)
    return episode


def _finished(actions, results) -> bool:
    for index, action in enumerate(actions):
        if action.type != "done":
            continue
        if index >= len(results) or results[index].success:
            return True
    return False
