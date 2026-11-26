"""Open a visible browser so a person can log in once. The profile stays in SESSION_DIR."""
import argparse

from session import open_context


def login_once(url: str, filler=None, headless: bool | None = None):
    """filler(page) performs the login. Without it, the window stays open until Enter."""
    from playwright.sync_api import sync_playwright
    show = True if headless is None else not headless
    if filler is not None and headless is None:
        show = False
    with sync_playwright() as playwright:
        context = open_context(playwright, headless=not show)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)
        if filler is None:
            print("Log in, in the browser window. Then press Enter here.")
            input()
        else:
            filler(page)
        context.close()


def main():
    parser = argparse.ArgumentParser(description="Save a logged-in browser profile")
    parser.add_argument("url")
    args = parser.parse_args()
    login_once(args.url)


if __name__ == "__main__":
    main()
