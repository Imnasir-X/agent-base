"""VLM decide(). Same signature as model_stub. Swap it in from config.MODEL.

Calls the xAI Responses API (OpenAI-compatible) with the SoM screenshot.
Docs: https://docs.x.ai/developers/model-capabilities/images/understanding
Structured output: text.format json_schema on the responses endpoint.
"""
import base64
import json
import os
import urllib.request

import config
from actions import Action

_TYPES = [
    "click_element", "type", "select", "key", "scroll",
    "goto", "wait", "done", "composite", "approval_needed",
]
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["actions"],
    "properties": {
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "params"],
                "properties": {
                    "type": {"type": "string", "enum": _TYPES},
                    "params": {"type": "object", "additionalProperties": True},
                },
            },
        }
    },
}


def decide(observation, state) -> list[Action]:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is not set")
    image = base64.b64encode(open(observation.som_screenshot_path, "rb").read()).decode()
    summary = {
        "task": state.task,
        "subgoal": state.subgoal,
        "last_3_actions": state.completed[-3:],
        "last_failure": state.last_failure,
    }
    elements = [{"id": el["id"], "tag": el["tag"], "text": el["text"]} for el in observation.elements]
    prompt = (
        "You are a GUI agent. Return exactly one next action. "
        "Use an element id from the list. Do not repeat last_failure. "
        f"State: {json.dumps(summary, ensure_ascii=False)}. "
        f"Elements: {json.dumps(elements, ensure_ascii=False)}."
    )
    body = {
        "model": config.XAI_MODEL,
        "store": False,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": f"data:image/png;base64,{image}", "detail": "low"},
                {"type": "input_text", "text": prompt},
            ],
        }],
        "text": {"format": {"type": "json_schema", "name": "agent_actions", "strict": True, "schema": _SCHEMA}},
    }
    request = urllib.request.Request(
        config.XAI_BASE_URL.rstrip("/") + "/responses",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode())
    return parse_actions(payload)


def parse_actions(payload: dict) -> list[Action]:
    text = payload.get("output_text") or ""
    if not text:
        for item in payload.get("output") or []:
            for bit in item.get("content") or []:
                if bit.get("type") in ("output_text", "text"):
                    text += bit.get("text") or ""
    data = json.loads(text)
    actions = [Action(str(raw["type"]), dict(raw.get("params") or {})) for raw in data["actions"]]
    if not actions:
        raise ValueError("model returned no actions")
    return actions
