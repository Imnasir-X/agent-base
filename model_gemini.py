"""Gemini Flash decide(). Same signature as the stub. Set HARNESS_MODEL=gemini.

Uses the generateContent REST API. No SDK. The key stays in GEMINI_API_KEY.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import config
from actions import Action


def decide(observation, state) -> list[Action]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    image = base64.b64encode(open(observation.som_screenshot_path, "rb").read()).decode()
    payload = _post(key, image, _prompt(observation, state))
    return _parse(payload)


def _prompt(observation, state) -> str:
    summary = {
        "task": state.task,
        "subgoal": state.subgoal,
        "last_3_actions": state.completed[-3:],
        "last_failure": state.last_failure,
    }
    elements = []
    for el in observation.elements:
        item = {
            "id": el["id"], "tag": el["tag"], "text": el["text"],
            "requires_approval": bool(el.get("requires_approval")),
        }
        if config.SHOW_CONTEXT:
            for key in ("under", "in", "pos"):
                if el.get(key):
                    item[key] = el[key]
        elements.append(item)
    hint = ""
    if any(el.get("pos") for el in elements):
        hint = " Duplicate labels include under (heading), in (section), and pos (n of n)."
    return (
        "You are a GUI agent. Return only JSON {\"actions\":[{\"type\":\"click_element\",\"params\":{\"id\":1}}]}. "
        "Do not return bounding boxes. "
        "Return exactly one next action. Use an element id from the list. Do not repeat last_failure. "
        "If requires_approval is true, return approval_needed instead of click_element. "
        "Allowed types: click_element, type, select, key, scroll, goto, wait, done, approval_needed. "
        "click_element params need id. type params need id and text. select params need id and option."
        + hint
        + f" State: {json.dumps(summary, ensure_ascii=False)}. "
        f"Elements: {json.dumps(elements, ensure_ascii=False)}."
    )


def _post(key: str, image: str, prompt: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + config.GEMINI_MODEL + ":generateContent"
    )
    generation = {"responseMimeType": "application/json", "maxOutputTokens": 400}
    if "lite" not in config.GEMINI_MODEL:
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    body = json.dumps({
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": image}},
            {"text": prompt},
        ]}],
        "generationConfig": generation,
    }).encode()
    last = "gemini request failed"
    for attempt in range(4):
        request = urllib.request.Request(
            url, data=body,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=150) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:240]
            last = f"gemini {exc.code}: {detail}"
            if exc.code not in (429, 500, 503) or attempt == 3:
                raise RuntimeError(last) from None
            time.sleep(30 if exc.code == 429 else 2 * (attempt + 1))
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            last = f"gemini transport: {reason}"
            if attempt == 3:
                raise RuntimeError(last) from None
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(last)


def _parse(payload: dict) -> list[Action]:
    parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text") or "" for part in parts if isinstance(part, dict)).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"model json: {text[:180]}") from None
    if isinstance(data, list):
        raws = data
    elif isinstance(data, dict) and ("actions" in data or "action" in data):
        raws = data["actions"] if "actions" in data else data["action"]
        raws = raws if isinstance(raws, list) else [raws]
    elif isinstance(data, dict):
        raws = [data]
    else:
        raise ValueError(f"model shape: {text[:180]}")
    actions = []
    for raw in raws:
        if not isinstance(raw, dict) or "type" not in raw:
            raise ValueError(f"model action: {text[:180]}")
        params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
        actions.append(Action(str(raw["type"]), dict(params)))
    if not actions:
        raise ValueError("model returned no actions")
    return actions
