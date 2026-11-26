"""Ask a person a question and return the answer. The agent loop calls this."""
import os
from pathlib import Path

import config


def _question(actions) -> str:
    for action in actions:
        if action.type == "ask_user":
            return str((action.params or {}).get("question") or "")
    return ""


def answer(actions, observation=None) -> str:
    question = _question(actions)
    path = config.LOG_DIR / "question.txt"
    path.write_text(question, encoding="utf-8")
    print(question, flush=True)
    reply_path = os.environ.get("HARNESS_ANSWER_FILE")
    if reply_path:
        return Path(reply_path).read_text(encoding="utf-8").strip()
    return input("answer: ").strip()
