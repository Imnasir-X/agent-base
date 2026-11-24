"""Named success checks. Tasks in eval_tasks.json refer to these by name."""


def url_contains(page, args) -> bool:
    return args["part"] in page.url


def input_value(page, args) -> bool:
    return page.locator(args["selector"]).input_value() == args["value"]


def text_visible(page, args) -> bool:
    loc = page.get_by_text(args["text"], exact=False)
    return loc.count() > 0 and loc.first.is_visible()


def checked(page, args) -> bool:
    return page.locator(args["selector"]).is_checked()


def select_value(page, args) -> bool:
    return page.locator(args["selector"]).input_value() == args["value"]


CHECKS = {
    "url_contains": url_contains,
    "input_value": input_value,
    "text_visible": text_visible,
    "checked": checked,
    "select_value": select_value,
}


def run_check(page, name: str, args: dict) -> bool:
    return bool(CHECKS[name](page, args or {}))
