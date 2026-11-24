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

Set `HARNESS_STUB_MODE=random` to prove the loop with no task policy. The default `heuristic` stub reads the task text so the eval can run with no model.
