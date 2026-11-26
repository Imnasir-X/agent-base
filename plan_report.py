"""Contract helper and the three planner numbers. No browser and no model."""
from plan import on_fail, on_pass, resolve, subgoal_text, validate


def measure(episodes) -> dict:
    """Last result per subgoal. A subgoal that was never reached counts as a miss."""
    texts = []
    for episode in episodes:
        for row in episode.get("results") or []:
            if row["text"] not in texts:
                texts.append(row["text"])
    rates = {}
    for text in texts:
        passed = 0
        for episode in episodes:
            last = False
            for row in episode.get("results") or []:
                if row["text"] == text:
                    last = bool(row["passed"])
            passed += int(last)
        rates[text] = round(passed / len(episodes), 4) if episodes else 0.0
    flags = [1.0 if episode.get("success") else 0.0 for episode in episodes]
    mean = round(sum(flags) / len(flags), 4) if flags else 0.0
    if len(flags) > 1:
        spread = (sum((item - mean) ** 2 for item in flags) / len(flags)) ** 0.5
    else:
        spread = 0.0
    return {"subgoal_pass_rate": rates, "fixture_pass_rate": mean, "fixture_stdev": round(spread, 4)}


def apply_case(case):
    event = case.get("event")
    if event == "validate":
        return validate(case.get("plan"))
    if event == "resolve":
        return resolve(case.get("text"), case.get("notes"))
    from state import TaskState
    data = case.get("state") or {}
    state = TaskState(
        data.get("task", ""), data.get("subgoal", ""), int(data.get("step") or 0),
        list(data.get("completed") or []), list(data.get("failures") or []),
        data.get("pending_approval"), data.get("model_name", "oracle"), data.get("last_failure"),
    )
    state.plan = data.get("plan")
    state.notes = dict(data.get("notes") or {})
    if event == "text":
        return subgoal_text(state)
    if event == "pass":
        on_pass(state, case.get("check"))
    else:
        on_fail(state, case.get("reason") or "check")
        if case.get("again"):
            on_fail(state, case.get("reason") or "check")
    return {
        "status": state.plan["status"], "index": state.plan["index"], "phase": state.plan["phase"],
        "replans": state.plan["replans"], "subgoal": state.subgoal, "notes": state.notes,
    }
