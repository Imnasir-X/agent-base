"""Secret lookup. The model names a secret. This module supplies the value."""
import json
import os

import config


def lookup(name: str) -> str:
    key = f"VAULT_{name}"
    if os.environ.get(key):
        return os.environ[key]
    path = config.ROOT / "secrets.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if name in data and data[name]:
            return str(data[name])
    raise KeyError(name)


def fill_secret(page, params):
    from actions import Action, ActionResult, execute_turn
    try:
        text = lookup(str(params.get("secret_name") or ""))
    except KeyError:
        return ActionResult(False, "exception")
    typed = {"id": params.get("id"), "text": text, "submit": bool(params.get("submit"))}
    return execute_turn(page, [Action("type", typed)])[0]


def install():
    from actions import register_action
    register_action("fill_secret", fill_secret)
