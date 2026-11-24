# agent-base

Minimal GUI-agent harness. Python, Playwright, local fixtures only.

This is a new repo. It does not modify [content-ops-harness](https://github.com/Imnasir-X/content-ops-harness).

The loop in `agent.py` does not import Playwright or a model SDK. `config.MODEL` selects `model_stub.decide` or `model_real.decide`. Actions are always a list. Every turn writes an intent line and an outcome line to `logs/*.jsonl`.

```powershell
cd E:\Projects\agent-base
python main.py --m0
python main.py --fixture home.html --task "Click About"
python eval_runner.py --runs 3 --baseline
python tests\test_harness.py
```

`model_real.py` calls the xAI Responses API (`XAI_API_KEY`, default model `grok-4.7`). Without a key, use the stub.

`HARNESS_STUB_MODE` is `heuristic` (default), `random`, or `done`. `done` always returns done and must fail every task. `random` clicks a real element and should score near zero. A Checkout button carries `data-requires-approval` and pauses unless an approver allows it.

Local captcha fixtures live under `eval_fixtures/captcha_*.html`. The text heuristic solves a checkbox, a delayed checkbox, a sum, a quoted code, and a Bangla answer. It does not read pixels, so the canvas code, the duplicate Verify button, and the duplicate picture tile stay misses. No external captcha service is called.

On this 28-task set the heuristic scores 0.6071 across 3 runs (stdev 0.0). Do-nothing and a seeded random clicker both score 0.0. That number is the text policy. A live VLM has not been scored, because `XAI_API_KEY` is unset.

```powershell
python replay.py logs\increment_r0.jsonl
```
