"""Prompt for a single plan. Nothing in the loop calls a model with it.

decide() still chooses one action. This prompt is only for emitting subgoals.
"""

PROMPT = """
Return one JSON object and nothing else. Shape:
{"goal":"...","subgoals":[
  {"text":"Open Users page","deterministic":true,
   "action":{"type":"goto","params":{"url":"{base}/users.html"}},
   "check":{"type":"url_contains","part":"users.html"}},
  {"text":"Fill name and email from row 3",
   "check":{"type":"value_equals","id":"name","value":"{row.name}"}},
  {"text":"Choose role Admin",
   "check":{"type":"value_equals","id":"role","value":"Admin"}},
  {"text":"Review form before saving",
   "check":{"type":"value_equals","id":"email","value":"{row.email}"}},
  {"text":"Save user","commit":true,
   "review":{"type":"value_equals","id":"email","value":"{row.email}"},
   "precondition":{"type":"enabled","id":"save"},
   "check":{"type":"text_visible","text":"{row.email}"}}
]}

Check types, and no others: url_contains, input_value, text_visible, checked,
select_value, value_equals, url_changed, enabled.
value_equals and input_value read a field. text_visible reads text on the page,
not an input's value. Use value_equals before a save. Use text_visible after the
page shows the saved value.

A deterministic subgoal must include action and is run with no model call.
action.type is one of goto, wait, click_element, type, select, key, scroll.
A commit subgoal must include review. The harness spends one read-only turn
before that commit and asks for approval on the commit itself.
Placeholders are {row.field} and {base} only. Do not emit {notes.field}.
Do not put a secret, a password, or a card number in the plan.
Do not add a second copy of the plan. One replan is the harness's job.
""".strip()
