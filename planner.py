"""Subgoal planner. The base returns the task, then 'done' after any success.

observation is part of the signature so a later planner can read the page
without an interface change. This version does not inspect it.
"""


def next_subgoal(state, observation) -> str:
    if observation is not None and state.completed:
        return "done"
    if state.completed:
        return "done"
    return state.task
