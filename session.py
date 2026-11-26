"""Persistent Chromium profile. agent.py does not import this module."""
import config

_ARGS = ["--disable-background-networking", "--disable-component-update", "--disable-sync"]


def open_context(playwright, headless: bool):
    config.SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(config.SESSION_DIR),
        headless=headless,
        viewport=config.VIEWPORT,
        device_scale_factor=1,
        args=_ARGS,
    )
