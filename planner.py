"""Subgoal planner.

With no plan, the base returns the task, then 'done' after any success.
observation is part of the signature so a later planner can read the page.
This version does not inspect it.

With a plan, the text is the current subgoal. One success does not skip the rest.
"""


def next_subgoal(state, observation) -> str:
    if getattr(state, "plan", None):
        from plan import subgoal_text
        return subgoal_text(state)
    if observation is not None and state.completed:
        return "done"
    if state.completed:
        return "done"
    return state.task
