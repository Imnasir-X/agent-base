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
