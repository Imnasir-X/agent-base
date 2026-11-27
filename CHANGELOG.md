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

## 2026-11-26 — Saved session, vault, approver, ask_user

These four pieces sit beside the loop. `agent.py` still does not import Playwright, a model SDK, or the filesystem. The 28-task list is unchanged. `login.html`, `inbox.html`, `opened.html`, and `code_gate.html` are not in `eval_tasks.json`.

`session.py` opens a persistent Chromium profile from `config.SESSION_DIR`. `login_once.py` lets a person log in once. A later task reuses that profile. The session test logs in through a filler, then "Click Open message" reaches `opened.html` with no `type` or `fill_secret` action in the log.

`vault.py` resolves `VAULT_<NAME>` or `secrets.json` and registers `fill_secret`. The model sends `secret_name` only. The value is typed inside `execute_turn` after the intent line is written. Password fields are omitted from element text, stored as `*` in the DOM hash, and painted black on the SoM shot.

`approver.approve` denies checkout, pay, delete, and send as whole words, plus the phrases "submit order" and "confirm order". A lone Confirm stays allowed so `modal_confirm` is unchanged. Eval mode does not read stdin. A denial sets `not_approved` and the loop continues, leaving `pending_approval` in place. A granted checkout still places the order.

`ask_user` pauses for `answerer`. With no answerer the loop stops on `waiting_user`. The reply is attached after the intent line, so the question turn's log does not contain the reply. `main.py` passes `ask_user.answer`. The eval runner does not, so a suite run cannot block on stdin.

The Gemini 28×5 gate was not re-run. Stub controls still have to stay in band: done at 0.0, random near 0, heuristic between 0.5 and 0.7.

## 2026-11-26 — Domain-bound secrets, commit approver, guard, replay check

A secret now carries an allowed host list (`VAULT_<NAME>_DOMAINS`, or `domains` in `secrets.json`). `fill_secret` on any other host types nothing and returns `exception`, without the value in the reason. Secret and OTP strings are held in memory and scrubbed from the JSONL copy. A text field that received one is marked `data-agent-secret`, omitted from the element text, and painted black on the raw shot as well as the SoM shot.

The approver treats typing and reading as free. A commit needs approval: `type` or `fill_secret` with `submit`, the Enter key, a submit button, pay/delete/order wording, a Bangla label such as পেমেন্ট, or any control inside a delete or pay dialog. A Confirm button whose dialog heading says Delete is denied. The fixtures for that are `place_order.html`, `buy_now.html`, `icon_delete.html`, `enter_submit.html`, `delete_modal.html`, and `bangla_pay.html`. They are not part of the 28-task list.

`guard.py` stops a run at the step ceiling (`HARNESS_MAX_STEPS`, default 8), after three identical failures, or when the page host is outside `HARNESS_ALLOW_DOMAINS` (default `127.0.0.1,localhost`).

`ask_user` replies are remembered before the next turn, so an OTP is not written to the log. Replay, when the log has a `check` line, runs that success check and compares it to the logged result.

Short approvals stay inside the running process: interactive mode blocks on stdin and the page stays open. This change does not add a jobs table or a Rust process. Exiting on approval would drop a half-filled form, and resuming later must not replay a commit.

## 2026-11-26 — Behavioral contract for the pure core

`core_cases.json` is the behavior of the parts that do not touch the browser or a model: guard, approver, planner, state advance, reward, vault host check, and log scrubbing. `behavior.py` runs those cases and exits 1 on any difference. Python is the reference. A later Rust port of the same operations has to return the same results before it can replace them. Changing an expected value is a behavior change and belongs in this file.

The contract locks a few edges that a rewrite would be tempted to "fix": a step limit is reported before a foreign host, only the last three failures count, `payments` is not the word `payment`, a bare Confirm is free unless the dialog or the form says delete or pay, an empty turn does not clear `last_failure`, and a longer secret is scrubbed before a shorter one.

## 2026-11-26 — A blocked attempt can fail the task

This takes one rule from Together AI's Hurdle and scores it here. The npm library is not installed, and no coding agent is run. There is no LLM judge.

`hurdle.py` reads the recorded session after the run. `agent.py` does not import it. An outcome of `not_approved`, `step_limit`, `repeated_failure`, or `domain_blocked` is a blocked attempt. A model error and `waiting_user` are not.

The default policy is `record`. The attempt is counted and the page check still decides the task. `checkout_gate` stays a pass when the commit was held and the order was not placed. A task that sets `hurdle` to `attempt_fails` fails when the log contains one of those attempts, even if the page check passed. `finish` writes a `verdict` line only for that policy. The 28-task list does not set it.

`core_cases.json` is version 2. The new cases lock that split: a held commit still passes under `record`, and the same log fails under `attempt_fails`.

## 2026-11-26 — Plan once, then one subgoal at a time

Tasks with no plan are unchanged: the subgoal is the whole task, and the first success still means done. The 28-task list does not include `users.html`. No model was called to write or run a plan.

When `state.plan` is set, the cursor walks the subgoals. A deterministic subgoal runs its `action` and does not call `decide`. Any other subgoal gets one `decide` call. A commit subgoal spends a read-only turn first: clicks on that turn are not executed, and the `review` check plus the precondition have to pass before the commit turn. The approver still sees the commit itself.

A failed check retries that same subgoal once and passes `last_failure` in. The page is not reloaded. A second failure ends the episode. `notes` receives a field only after `value_equals` or `input_value` passes. `{row.field}` is the spreadsheet value bound at the start. `{notes.field}` does not resolve before that.

`text_visible` reads text on the page, not an input's value, so the pre-save checks use `value_equals`. The hand-written template is `plans/create_user.json`. `planner_prompt.py` holds the prompt that would ask a model for a plan in that shape. The loop does not send it.

`core_cases.json` is version 3. The new cases lock that one successful action does not finish a plan, that a commit without a review is rejected, and that the second failed check stops the episode. `measure` reports per-subgoal pass rate, fixture pass rate, and fixture stdev. A subgoal a run never reached counts as a miss.

The Save button on `users.html` stayed disabled because the page used `var name` for the name field. In a browser that assigns `window.name`, so the element was stringified and the refresh always saw a missing value. `select` is not the cause: Playwright's `select_option` fires `input` and then `change`, and a page that listens for those events enables its button. The fixture now names the elements `nameBox`, `emailBox`, `roleBox`, and `saveButton`.

A value check does not copy a password, a `data-agent-secret` field, a code/otp/pin id, or a vault value into `notes`. Whatever is stored is then passed through the same scrubber as the JSONL. An invalid plan, or one with an unbound `{row.*}` or `{base}`, is refused by `try_attach` and the task stays on the unplanned loop. No model is asked to write a plan yet.

`plan_stability.run_episode` is the adapter for the external stability harness. With the plan-following stub, baseline was 30/30, stdev 0. `code_submit` was 10/10 and never left the page. `duplicate_save` and `late_save` were 0/10: every episode reached Save and missed it, with 20 decoy hits each, because the one replan clicked again inside the same failure. Flash-Lite has not run this plan.

## 2026-11-27 — Busy Save, duplicate labels, eval submit grant

`enabled` now means the control is not disabled, not `aria-disabled="true"`, and not `aria-busy="true"`. A retry waits up to 3 seconds and checks that precondition again. A control that is still busy fails as `precondition: busy`. The plan-following stub still clicks the first exact Save, and a test locks that `duplicate_save` miss. Duplicate labels gain `under`, `in`, and `pos` on the element list the model sees. `HARNESS_CONTEXT=0` leaves those fields out.

Of the 28 tasks, only `multistep_form` needs a submit to land. Its check stays "Submitted". Eval writes an `eval_grant` line and allows that benign submit. Pay, delete, checkout, and order stay denied, and `checkout_gate` still expects the commit to be held. `type_submit` and `query_enter` are in the retired 20-task table, not in the 28, so they are not 0.107 of this score. One task is 0.0357. The approver itself is unchanged.

`late_save` with the plan-following stub, 10 episodes × 3 rounds, on 2026-11-27: pass 1.00, stdev 0.000, streak 30, per-subgoal 1.00 1.00 1.00 1.00 1.00. Gate passed. Each episode still recorded one `early_save`, because an earlier input's timer can clear `aria-busy` while the click hold is still running. The retry then saved the user. Flash-Lite has not run yet.
