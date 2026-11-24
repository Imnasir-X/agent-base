"""Entry point for one task. Picks the decide function from config.MODEL."""
import argparse

import config
from agent import run_episode
from state import TaskState


def load_decide():
    if config.MODEL == "real":
        from model_real import decide
        return decide
    if config.MODEL == "gemini":
        from model_gemini import decide
        return decide
    from model_stub import decide
    return decide


def _browser():
    from playwright.sync_api import sync_playwright
    return sync_playwright()


def _server():
    from eval_runner import serve
    return serve()


def capture_m0():
    """Open the local m0 fixture and save runs/m0.png. No live sites."""
    httpd = _server()
    port = httpd.server_address[1]
    dest = config.RUN_DIR / "m0.png"
    with _browser() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1)
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{port}/m0.html")
        page.wait_for_timeout(config.SETTLE_MS)
        page.screenshot(path=str(dest))
        browser.close()
    httpd.shutdown()
    return dest


def run_task(fixture: str, task: str, max_steps: int = 5) -> dict:
    httpd = _server()
    port = httpd.server_address[1]
    config.LOG_PATH = config.LOG_DIR / "task.jsonl"
    with _browser() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1)
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{port}/{fixture}")
        state = TaskState(task, task, 0, [], [], None, config.MODEL, None)
        episode = run_episode(page, state, load_decide(), None, max_steps)
        episode["url"] = page.url
        browser.close()
    httpd.shutdown()
    return episode


def main():
    parser = argparse.ArgumentParser(description="Run one local fixture task")
    parser.add_argument("--m0", action="store_true", help="Screenshot eval_fixtures/m0.html")
    parser.add_argument("--fixture", default="home.html")
    parser.add_argument("--task", default="Click About")
    parser.add_argument("--max-steps", type=int, default=config.MAX_STEPS)
    args = parser.parse_args()
    if args.m0:
        print(capture_m0())
        return
    print(run_task(args.fixture, args.task, args.max_steps))


if __name__ == "__main__":
    main()
