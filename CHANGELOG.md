# Changelog

## 2026-11-24 — Copy `<label>` text onto elements

`perception.observe` previously built each element's text from inner text, value, aria-label, placeholder, and name. A labeled input such as `<label for="search">Search</label><input id="search">` came back with an empty text, so the stub had nothing to match and returned `done` on the first turn.

The stamp step now also copies the `<label for>` text (and a wrapping label). No other module changed.

Baseline is `BASELINE.md` (20 tasks, 3 runs, stub heuristic):

| metric | before mean | before stdev | after mean | after stdev |
|---|---:|---:|---:|---:|
| success_rate | 0.65 | 0.0 | 1.0 | 0.0 |
| avg_turns | 1.75 | 0.0 | 2.15 | 0.0 |
| avg_latency_ms | 1884.8 | 4.7604 | 2210.0 | 2.647 |

Success rate rose by 0.35. The baseline success stdev is 0 because the misses were the same on every run, so the gain sits outside that spread. Latency stdev stayed small and nonzero (4.76 before, 2.65 after).

Tasks at 0/3 before this change, all passing in the after run: `type_search`, `type_submit`, `type_name_email`, `check_agree`, `note`, `quantity`, `query_enter`. They used to log a single `done` and stop. Average turns rose because those tasks now perform the type or click.

Evidence: `BASELINE.md` rows for those seven tasks, and `logs/type_search_r0.jsonl` after the change (a `type` action whose field text includes Search, then a passing check).

## 2026-11-24 — Hard fixtures, controls, replay, local captchas

The easy 20-task set scored 1.0 after the label fix, so the checks were too weak for a decent policy. The set is now 28 local tasks: scrolling, dropdowns, modals, delayed content, duplicate labels, a multi-step form, Bangla labels, a Checkout button that pauses for approval, and eight captcha pages.

Captcha pages are local HTML only. The text heuristic solves the human checkbox, the delayed checkbox, `3 + 4`, the quoted code, and the Bangla answer. It does not read pixels, so the canvas code stays a miss, as do the first Verify button and the first bus tile. No external captcha service is called. `XAI_API_KEY` is unset, so this is not a live VLM score.

`replay.py` re-executes a log's action list on a fresh fixture server. A `not_approved` outcome is skipped. Failed captcha logs and the checkout pause log replay with matching results.

Controls and the 3-run heuristic measurement:

| policy | runs | success_rate mean | success_rate stdev |
|---|---:|---:|---:|
| done (always done) | 1 | 0.0 | 0.0 |
| random (seed 0) | 1 | 0.0 | 0.0 |
| heuristic | 3 | 0.6071 | 0.0 |

Heuristic avg_turns mean 2.1786 (stdev 0.0). Heuristic avg_latency_ms mean 2467.0595 (stdev 9.1144).

Do-nothing failed all 28 tasks. Random passed none. Heuristic passed the same 17 tasks on every run (stdev 0) and missed the same 11. Latency stdev is 9.11 ms. The per-task rows are in `BASELINE.md` under "Hard fixtures and captchas".

## 2026-11-24 — Gemini flash-lite baseline

A fresh stub eval before this run matched the hard-fixture success rate of 0.6071 and the turn count. Latency on that rerun was 2467.7 ms (stdev 8.92), against 2467.1 ms (stdev 9.11) in the stub section of `BASELINE.md`.

The VLM run is 28 tasks, 5 runs, `gemini-3.5-flash-lite`. Stronger Gemini models were over quota or returned 503, so this is not a Pro baseline.

| metric | mean | stdev |
|---|---:|---:|
| success_rate | 0.5286 | 0.0267 |
| avg_turns | 2.3143 | 0.0474 |
| avg_latency_ms | 11031.3429 | 2018.9554 |

Success variance is no longer zero. `click_docs` was 4/5, `reveal_details` 4/5, `second_show` 2/5, `captcha_bangla` 4/5.

`checkout_gate` scored 0/5 because `approval_held` required the word "checkout" in the action params. The other stable misses are the model clicking the first trap or a decoy link.

`delayed_ready` is a model miss, not a wait bug. The saved screenshot for run 3 shows only the Leave links. Observe had already reached network idle and the 500ms settle. The Ready button is created at 1200ms, so it was not on the page yet. The model clicked element 1, Leave 1, and the page went to `gone.html`.

## 2026-11-24 — Scoring fix for checkout_gate

This is a scoring fix. The logged actions did not change.

`approval_held` now treats a paused element id as a match when that element's visible text contains the expected word. Rescored from the five `logs/checkout_gate_r*.jsonl` files: runs 0–2 are `approval_needed` on id 19, which is the Checkout button, with `not_approved` and no order placed. Runs 3–4 are `approval_needed` with empty params, so they stay misses. `checkout_gate` moves from 0/5 to 3/5.

Per-run success counts become 15, 15, 17, 15, 15 out of 28.

| metric | before mean | before stdev | after mean | after stdev |
|---|---:|---:|---:|---:|
| success_rate | 0.5286 | 0.0267 | 0.55 | 0.0286 |

Turns and latency are unchanged, because this does not re-execute the episodes. The band for later steps is success_rate about 0.55, stdev 0.0286.
