"""Place hints for duplicate labels. Unique labels stay bare.

under is the nearest preceding heading. in is the form or section.
pos is the 1-based place among controls that share the same text.
"""

ANNOTATE_JS = """
(rows) => {
  const counts = {};
  for (const row of rows) {
    const key = String(row.text || '').trim();
    if (key) counts[key] = (counts[key] || 0) + 1;
  }
  const seen = {};
  const out = {};
  const underOf = (el) => {
    let node = el;
    while (node) {
      let prev = node.previousElementSibling;
      while (prev) {
        if (/^H[1-6]$/.test(prev.tagName)) return (prev.innerText || '').trim();
        prev = prev.previousElementSibling;
      }
      node = node.parentElement;
    }
    return '';
  };
  const inOf = (el) => {
    const box = el.closest('fieldset, form, section, [role="group"]');
    if (!box) return '';
    const legend = box.querySelector(':scope > legend');
    if (legend) return (legend.innerText || '').trim();
    return (box.getAttribute('aria-label') || box.id || '').trim();
  };
  for (const row of rows) {
    const key = String(row.text || '').trim();
    if (!key || counts[key] < 2) continue;
    seen[key] = (seen[key] || 0) + 1;
    const el = document.querySelector('[data-agent-id="' + row.id + '"]');
    if (!el) continue;
    out[String(row.id)] = {
      under: underOf(el),
      in: inOf(el),
      pos: seen[key] + ' of ' + counts[key],
    };
  }
  return out;
}
"""


def annotate(page, elements: list[dict]) -> list[dict]:
    if not elements:
        return elements
    rows = [{"id": el["id"], "text": el.get("text") or ""} for el in elements]
    hints = page.evaluate(ANNOTATE_JS, rows) or {}
    for el in elements:
        hint = hints.get(str(el["id"])) or {}
        for key in ("under", "in", "pos"):
            if hint.get(key):
                el[key] = hint[key]
    return elements
