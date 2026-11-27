"""Eval may let a benign submit through when the task opts in.

The grant is a JSONL line. Pay, delete, checkout, and order stay denied.
In the 28, only multistep_form asks for this. checkout_gate still expects
the commit to be held. type_submit and query_enter are not in the 28.
"""
from approver import _blob, _el, approve, is_risky
from logger import log_grant

_BLOCK = (
    "checkout", "pay", "payment", "delete", "buy", "purchase", "order",
    "পেমেন্ট", "মুছ", "কিনুন", "অর্ডার",
)


def _benign(actions, observation) -> bool:
    for action in actions:
        el = _el(observation, (action.params or {}).get("id"))
        blob = _blob(action, el)
        if any(word in blob for word in _BLOCK):
            return False
    return True


def approve_task(task, actions, observation) -> bool:
    opted = (task or {}).get("approve") == "benign_submit"
    if opted and is_risky(actions, observation) and _benign(actions, observation):
        log_grant(str(task.get("name") or ""), "benign_submit")
        return True
    return approve(actions, observation)
