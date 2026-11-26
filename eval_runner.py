"""Run every local fixture task several times and report mean and stdev.

Page traffic to anything but localhost is aborted. Fixtures are served here.
"""
import argparse
import json
import statistics
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config
from agent import run_episode
from approver import approve
from eval_checks import run_check
from main import load_decide
from reward import reward
from state import TaskState
from vault import install as install_vault
install_vault()

class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return


def serve(port: int = 0):
    handler = partial(_Quiet, directory=str(config.FIXTURES))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _guard(route, blocked: dict):
    url = route.request.url
    if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
        route.continue_()
        return
    blocked["n"] += 1
    route.abort()


def run_eval(runs: int = 3) -> dict:
    tasks = json.loads((config.ROOT / "eval_tasks.json").read_text(encoding="utf-8"))
    httpd = serve()
    port = httpd.server_address[1]
    decide = load_decide()
    rows = []
    blocked = {"n": 0}
    from playwright.sync_api import sync_playwright
    from session import open_context
    with sync_playwright() as playwright:
        context = open_context(playwright, True)
        for task in tasks:
            for run_i in range(runs):
                rows.append(_one(context, port, task, run_i, decide, blocked))
        context.close()
    httpd.shutdown()
    if blocked["n"]:
        raise RuntimeError(f"blocked {blocked['n']} non-local requests")
    return _summary(tasks, rows, runs)


def _one(context, port, task, run_i, decide, blocked) -> dict:
    config.LOG_PATH = config.LOG_DIR / f"{task['name']}_r{run_i}.jsonl"
    if config.LOG_PATH.exists():
        config.LOG_PATH.unlink()
    page = context.new_page()
    page.route("**/*", lambda route: _guard(route, blocked))
    page.goto(f"http://127.0.0.1:{port}/{task['start']}")
    label = config.GEMINI_MODEL if config.MODEL == "gemini" else f"{config.MODEL}:{config.STUB_MODE}"
    state = TaskState(task["goal"], task["goal"], 0, [], [], None, label, None)
    episode = run_episode(page, state, decide, approve, int(task.get("max_steps") or config.MAX_STEPS))
    ok = run_check(page, task["check"], task.get("args") or {}, state)
    episode["success"] = bool(ok)
    episode["reward"] = reward(episode)
    page.close()
    return {"name": task["name"], "run": run_i, "success": int(ok),
            "turns": episode["num_turns"], "latency": episode["latency_ms"]}


def _summary(tasks, rows, runs: int) -> dict:
    per_run = []
    for run_i in range(runs):
        subset = [row for row in rows if row["run"] == run_i]
        per_run.append((
            sum(row["success"] for row in subset) / len(subset),
            sum(row["turns"] for row in subset) / len(subset),
            sum(row["latency"] for row in subset) / len(subset),
        ))

    def pack(index):
        vals = [item[index] for item in per_run]
        spread = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        return {"mean": round(statistics.mean(vals), 4), "stdev": round(spread, 4)}

    by_task = []
    for task in tasks:
        subset = [row for row in rows if row["name"] == task["name"]]
        by_task.append({
            "name": task["name"],
            "successes": sum(row["success"] for row in subset),
            "runs": runs,
            "avg_turns": round(statistics.mean(row["turns"] for row in subset), 3),
            "avg_latency_ms": round(statistics.mean(row["latency"] for row in subset), 1),
        })
    return {
        "n_tasks": len(tasks),
        "runs_per_task": runs,
        "success_rate": pack(0),
        "avg_turns": pack(1),
        "avg_latency_ms": pack(2),
        "tasks": by_task,
    }


def write_baseline(stats: dict, path=None) -> None:
    path = path or (config.ROOT / "BASELINE.md")
    s, t, lat = stats["success_rate"], stats["avg_turns"], stats["avg_latency_ms"]
    lines = [
        "# Baseline",
        "",
        f"Tasks: {stats['n_tasks']}. Runs per task: {stats['runs_per_task']}. Model: {config.MODEL} / {config.STUB_MODE}.",
        "",
        f"- success_rate mean {s['mean']} stdev {s['stdev']}",
        f"- avg_turns mean {t['mean']} stdev {t['stdev']}",
        f"- avg_latency_ms mean {lat['mean']} stdev {lat['stdev']}",
        "",
        "| task | successes | avg_turns | avg_latency_ms |",
        "|---|---:|---:|---:|",
    ]
    for row in stats["tasks"]:
        lines.append(f"| {row['name']} | {row['successes']}/{row['runs']} | {row['avg_turns']} | {row['avg_latency_ms']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Evaluate the harness on local fixtures")
    parser.add_argument("--runs", type=int, default=config.EVAL_RUNS)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    stats = run_eval(args.runs)
    print(json.dumps({k: stats[k] for k in ("n_tasks", "runs_per_task", "success_rate", "avg_turns", "avg_latency_ms")}, indent=2))
    if args.baseline:
        write_baseline(stats)
        print(f"wrote {config.ROOT / 'BASELINE.md'}")


if __name__ == "__main__":
    main()
