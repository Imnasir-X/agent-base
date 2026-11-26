"""Secret lookup. The model names a secret. This module supplies the value.

Each secret has an allowed host list. A page on any other host gets nothing.
The value is remembered only so logs can be scrubbed. It is never returned
in an error string.
"""
import json
import os
from urllib.parse import urlparse

import config
from logger import remember


def _host_ok(host: str, domains) -> bool:
    host = (host or "").lower()
    allowed = [str(item).lower() for item in domains or []]
    return bool(host) and host in allowed


def _parse(raw):
    if isinstance(raw, dict):
        return str(raw.get("value") or ""), list(raw.get("domains") or [])
    return "", []


def _load(name: str):
    env = os.environ.get(f"VAULT_{name}")
    if env:
        domains = os.environ.get(f"VAULT_{name}_DOMAINS", "")
        return env, [item.strip() for item in domains.split(",") if item.strip()]
    path = config.ROOT / "secrets.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if name in data and data[name]:
            return _parse(data[name])
    raise KeyError(name)


def lookup(name: str, host: str) -> str:
    value, domains = _load(name)
    if not value or not _host_ok(host, domains):
        raise KeyError(name)
    return value


def _mark(page, eid) -> None:
    try:
        page.locator(f'[data-agent-id="{int(eid)}"]').evaluate(
            "el => el.setAttribute('data-agent-secret','1')"
        )
    except Exception:
        return


def fill_secret(page, params):
    from actions import Action, ActionResult, execute_turn
    host = (urlparse(page.url).hostname or "").lower()
    try:
        text = lookup(str(params.get("secret_name") or ""), host)
    except KeyError:
        return ActionResult(False, "exception")
    remember(text)
    typed = {"id": params.get("id"), "text": text, "submit": bool(params.get("submit"))}
    result = execute_turn(page, [Action("type", typed)])[0]
    _mark(page, params.get("id"))
    return result


_wrapped = False


def install():
    global _wrapped
    from actions import register_action, _RUN
    register_action("fill_secret", fill_secret)
    if _wrapped:
        return
    raw = _RUN["type"]

    def typed(page, params):
        result = raw(page, params)
        text = str((params or {}).get("text") or "")
        if text and text in _known():
            _mark(page, (params or {}).get("id"))
        return result

    register_action("type", typed)
    _wrapped = True


def _known() -> set[str]:
    from logger import held
    return held()
