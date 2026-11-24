"""Screenshot, DOM stamp, SoM overlay, and a stable DOM hash.

observe waits for network idle, settles, stamps data-agent-id on clickable
elements, saves a raw shot and a numbered SoM shot, and returns both paths.
"""
import hashlib
import time
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw

import config

STAMP_JS = """
() => {
  const sel = 'a, button, input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="tab"]';
  const out = [];
  let id = 1;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || s.visibility === 'hidden' || s.display === 'none') continue;
    el.setAttribute('data-agent-id', String(id));
    el.setAttribute('data-agent-x', String(Math.round(r.x)));
    el.setAttribute('data-agent-y', String(Math.round(r.y)));
    el.setAttribute('data-agent-w', String(Math.round(r.width)));
    el.setAttribute('data-agent-h', String(Math.round(r.height)));
    let labelText = '';
    if (el.id) {
      const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lab) labelText = lab.innerText || '';
    }
    const wrap = el.closest('label');
    if (!labelText && wrap) labelText = wrap.innerText || '';
    const bits = [labelText, el.innerText || '', el.value || '', el.getAttribute('aria-label') || '',
      el.getAttribute('placeholder') || '', el.getAttribute('name') || ''];
    const text = bits.map(t => String(t).trim()).filter(Boolean).join(' ').replace(/\\s+/g, ' ').slice(0, 140);
    out.push({id, tag: el.tagName.toLowerCase(), text, x: Math.round(r.x), y: Math.round(r.y),
      w: Math.round(r.width), h: Math.round(r.height)});
    id += 1;
  }
  return out;
}
"""

HASH_JS = """
() => {
  const root = document.documentElement.cloneNode(true);
  root.querySelectorAll('*').forEach(el => {
    [...el.attributes].forEach(attr => {
      if (attr.name.startsWith('data-agent-')) el.removeAttribute(attr.name);
    });
  });
  const vals = [...document.querySelectorAll('input, textarea, select')].map(el => {
    return (el.id || el.name || '') + '=' + (el.value || '') + (el.checked ? ':1' : ':0');
  });
  return root.innerHTML + '\\n' + vals.join('|') + '\\n' + window.scrollY;
}
"""


@dataclass
class Observation:
    raw_screenshot_path: str
    som_screenshot_path: str
    elements: list[dict]
    url: str
    title: str
    dom_hash: str


def dom_hash(page) -> str:
    raw = page.evaluate(HASH_JS)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def pixels_differ(before: bytes, after: bytes) -> bool:
    """True when sampled pixels differ. Not sufficient by itself to call an action done."""
    left = Image.open(BytesIO(before)).convert("RGB").tobytes()
    right = Image.open(BytesIO(after)).convert("RGB").tobytes()
    if len(left) != len(right):
        return True
    idxs = range(0, len(left), 48)
    ratio = sum(left[i] != right[i] for i in idxs) / max(len(idxs), 1)
    return ratio > config.PIXEL_DIFF_THRESHOLD


def _draw(raw_path, som_path, elements: list[dict]) -> None:
    image = Image.open(raw_path).convert("RGB")
    pen = ImageDraw.Draw(image)
    for el in elements:
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        pen.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
        pen.rectangle([x, max(0, y - 14), x + 22, max(0, y)], fill=(255, 0, 0))
        pen.text((x + 2, max(0, y - 13)), str(el["id"]), fill=(255, 255, 255))
    image.save(som_path)


def observe(page) -> Observation:
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(config.SETTLE_MS)
    elements = page.evaluate(STAMP_JS)
    stamp = time.time_ns()
    raw_path = config.RUN_DIR / f"{stamp}_raw.png"
    som_path = config.RUN_DIR / f"{stamp}_som.png"
    page.screenshot(path=str(raw_path))
    _draw(raw_path, som_path, elements)
    return Observation(str(raw_path), str(som_path), elements, page.url, page.title(), dom_hash(page))
