# Baseline

Tasks: 20. Runs per task: 3. Model: stub / heuristic.

- success_rate mean 0.65 stdev 0.0
- avg_turns mean 1.75 stdev 0.0
- avg_latency_ms mean 1884.8 stdev 4.7604

| task | successes | avg_turns | avg_latency_ms |
|---|---:|---:|---:|
| click_about | 3/3 | 2 | 2386.3 |
| click_contact | 3/3 | 2 | 2347.3 |
| click_docs | 3/3 | 2 | 2343.3 |
| click_bangla | 3/3 | 2 | 2364.3 |
| type_search | 0/3 | 1 | 1111.7 |
| type_submit | 0/3 | 1 | 1116 |
| type_name_email | 0/3 | 1 | 1126.3 |
| select_blue | 3/3 | 2 | 1838.3 |
| check_agree | 0/3 | 1 | 1108 |
| save_draft | 3/3 | 2 | 1943.3 |
| delete_draft | 3/3 | 2 | 1945.3 |
| counter | 3/3 | 2 | 1940 |
| reveal | 3/3 | 3 | 3135.3 |
| tabs | 3/3 | 2 | 1952 |
| tall | 3/3 | 2 | 1985.7 |
| menu | 3/3 | 3 | 3337 |
| note | 0/3 | 1 | 1118.7 |
| quantity | 0/3 | 1 | 1103 |
| continue_on | 3/3 | 2 | 2381.7 |
| query_enter | 0/3 | 1 | 1112.3 |

## Hard fixtures and captchas (2026-11-24)

The table above is the earlier 20-task set. This measurement is the harder 28-task set, including local captcha pages. Model: stub / heuristic. `XAI_API_KEY` was unset, so this is the text policy, not a live VLM.

- success_rate mean 0.6071 stdev 0.0
- avg_turns mean 2.1786 stdev 0.0
- avg_latency_ms mean 2467.0595 stdev 9.1144

Same 17 tasks passed on all 3 runs. Do-nothing (`HARNESS_STUB_MODE=done`, 1 run) scored 0.0 with every task failed. Random clicks with seed 0 scored 0.0.

| task | successes | avg_turns | avg_latency_ms |
|---|---:|---:|---:|
| scroll_finish | 3/3 | 2 | 2076.7 |
| select_district | 3/3 | 2 | 1890 |
| bangla_name | 3/3 | 2 | 1921.7 |
| multistep_form | 3/3 | 3 | 2808.3 |
| modal_confirm | 3/3 | 3 | 2950.3 |
| delayed_ready | 3/3 | 3 | 3420.3 |
| checkout_gate | 3/3 | 1 | 1124.7 |
| click_docs | 3/3 | 2 | 2461.7 |
| check_terms | 3/3 | 2 | 2064.3 |
| increment | 3/3 | 2 | 2080 |
| reveal_details | 3/3 | 3 | 3337.7 |
| note_field | 3/3 | 2 | 1986.3 |
| dup_save | 0/3 | 2 | 2458 |
| dup_bangla | 0/3 | 2 | 2419 |
| modal_decoy | 0/3 | 2 | 2429.3 |
| delayed_trap | 0/3 | 2 | 2405 |
| second_email | 0/3 | 2 | 1860.3 |
| second_select | 0/3 | 2 | 5829 |
| second_show | 0/3 | 2 | 2372 |
| fake_finish | 0/3 | 2 | 2417 |
| captcha_checkbox | 3/3 | 2 | 1997.3 |
| captcha_delay | 3/3 | 3 | 3344.3 |
| captcha_math | 3/3 | 3 | 2682.3 |
| captcha_code | 3/3 | 2 | 1860.3 |
| captcha_bangla | 3/3 | 2 | 1881.7 |
| captcha_image | 0/3 | 2 | 2109 |
| captcha_decoy | 0/3 | 2 | 2411.7 |
| captcha_tiles | 0/3 | 2 | 2479.3 |
