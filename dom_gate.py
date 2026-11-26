from urllib.parse import urlparse
from playwright.sync_api import Page, Route

SANITIZE_JS = """
() => {
  const stripped = [];
  const SKIP_TAGS = new Set(['STYLE', 'SCRIPT', 'NOSCRIPT', 'TEMPLATE']);
  const HIDDEN_ATTRS = ['aria-label', 'alt', 'title', 'placeholder'];

  function parseRGBA(str) {
    if (!str || str === 'transparent') return [0, 0, 0, 0];
    const m = str.match(/\\d+(\\.\\d+)?/g);
    if (!m) return [0, 0, 0, 1];
    const nums = m.map(Number);
    return nums.length === 3 ? [...nums, 1] : nums;
  }

  function relativeLuminance(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map(v => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }

  function contrastRatio(c1, c2) {
    const l1 = relativeLuminance(c1[0], c1[1], c1[2]);
    const l2 = relativeLuminance(c2[0], c2[1], c2[2]);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  function getEffectiveBg(el) {
    let cur = el;
    while (cur && cur !== document.documentElement) {
      const bg = parseRGBA(getComputedStyle(cur).backgroundColor);
      if (bg[3] > 0.1) return bg;
      cur = cur.parentElement;
    }
    const rootBg = parseRGBA(getComputedStyle(document.documentElement).backgroundColor);
    return rootBg[3] > 0.1 ? rootBg : [255, 255, 255, 1];
  }

  function getAncestorHideReason(el) {
    let cur = el;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      const style = getComputedStyle(cur);
      if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') return 'css-hidden';
      if (parseFloat(style.opacity) < 0.05) return 'zero-opacity';
      const rect = cur.getBoundingClientRect();
      const clipped = (style.overflow === 'hidden' || style.overflow === 'clip' || style.overflowX === 'hidden' || style.overflowY === 'hidden');
      if (clipped && (rect.width <= 1 || rect.height <= 1)) return 'zero-dimensions-clipped';
      if (style.clipPath && style.clipPath.includes('100%')) return 'css-clipped';
      cur = cur.parentElement;
    }
    return null;
  }

  const commentWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
  const comments = [];
  let cNode;
  while ((cNode = commentWalker.nextNode())) {
    if (cNode.nodeValue && cNode.nodeValue.trim()) comments.push(cNode);
  }
  for (const comment of comments) {
    stripped.push({ tag: '#comment', reason: 'html-comment', preview: comment.nodeValue.trim().slice(0, 120) });
    comment.remove();
  }

  const textWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const toRemove = [];
  let tNode;
  while ((tNode = textWalker.nextNode())) {
    const text = (tNode.nodeValue || '').trim();
    if (!text) continue;
    const el = tNode.parentElement;
    if (!el || SKIP_TAGS.has(el.tagName)) continue;

    const style = getComputedStyle(el);
    let reason = getAncestorHideReason(el);

    if (!reason) {
      if (parseFloat(style.fontSize) < 4) reason = 'micro-font';
      else if (Math.abs(parseFloat(style.textIndent) || 0) > 500) reason = 'text-indent-hidden';
      else {
        const fg = parseRGBA(style.color);
        if (fg[3] < 0.1) reason = 'transparent-text';
        else if (contrastRatio(fg, getEffectiveBg(el)) < 1.4) reason = 'low-contrast-camo';
      }
    }

    if (!reason) {
      const range = document.createRange();
      range.selectNodeContents(tNode);
      const rect = range.getBoundingClientRect();
      if (rect.width <= 0.5 || rect.height <= 0.5) reason = 'zero-dimensions';
      else if (rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth + 200) reason = 'off-screen';
      else {
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        if (cx >= 0 && cy >= 0 && cx < window.innerWidth && cy < window.innerHeight) {
          const topEl = document.elementFromPoint(cx, cy);
          if (topEl && !el.contains(topEl) && !topEl.contains(el)) {
            const topBg = parseRGBA(getComputedStyle(topEl).backgroundColor);
            const topOpacity = parseFloat(getComputedStyle(topEl).opacity);
            if ((topBg[3] > 0.5 && topOpacity > 0.5) || ['IMG', 'SVG', 'CANVAS', 'IFRAME'].includes(topEl.tagName)) {
              reason = 'occluded-overlay';
            }
          }
        }
      }
    }

    if (reason) toRemove.push({ node: tNode, tag: el.tagName.toLowerCase(), reason, preview: text.slice(0, 120) });
  }

  for (const item of toRemove) {
    stripped.push({ tag: item.tag, reason: item.reason, preview: item.preview });
    item.node.remove();
  }

  for (const el of Array.from(document.querySelectorAll('body *'))) {
    if (SKIP_TAGS.has(el.tagName)) continue;
    const hideReason = getAncestorHideReason(el);
    const rect = el.getBoundingClientRect();
    const offScreen = rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth + 200;
    if (hideReason || offScreen) {
      for (const attr of HIDDEN_ATTRS) {
        const val = el.getAttribute(attr);
        if (val && val.trim()) {
          stripped.push({ tag: el.tagName.toLowerCase(), reason: `hidden-attr:${attr}`, preview: val.trim().slice(0, 120) });
          el.removeAttribute(attr);
        }
      }
    }
  }
  return stripped;
}
"""


class DomGateError(Exception):
    pass


def normalize_origin(url: str) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return ""
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"


class DomGate:
    def __init__(self, page: Page, allowed_origins: set[str]):
        self.page = page
        self.context = page.context
        self.allowed_origins = {normalize_origin(o) for o in allowed_origins}
        self.blocked_events: list[dict] = []
        self._install_context_network_gate()

    def _is_allowed(self, url: str) -> bool:
        if url.startswith(("about:", "data:", "blob:")):
            return True
        return normalize_origin(url) in self.allowed_origins

    def _install_context_network_gate(self):
        def handle_route(route: Route):
            req = route.request
            if not self._is_allowed(req.url):
                self.blocked_events.append({"type": "BLOCKED_EGRESS", "method": req.method, "url": req.url})
                print(f"[DOM-GATE BLOCKED] Unauthorized {req.method} request: {req.url}")
                route.abort("blockedbyclient")
                return
            route.continue_()
        self.context.route("**/*", handle_route)

    def safe_goto(self, url: str) -> list[dict]:
        if not self._is_allowed(url):
            self.blocked_events.append({"type": "BLOCKED_NAV", "url": url})
            raise DomGateError(f"Blocked navigation to untrusted origin: {url}")
        self.page.goto(url, wait_until="networkidle")
        return self.sanitize_dom()

    def safe_fill(self, selector: str, value: str, is_sensitive: bool = False):
        if not self._is_allowed(self.page.url):
            self.blocked_events.append({"type": "BLOCKED_FILL", "url": self.page.url, "selector": selector})
            raise DomGateError(f"Blocked input on untrusted origin: {self.page.url}")
        locator = self.page.locator(selector).first
        if is_sensitive and not locator.is_visible():
            self.blocked_events.append({"type": "BLOCKED_HIDDEN_FILL", "url": self.page.url, "selector": selector})
            raise DomGateError(f"Blocked sensitive fill into hidden input: {selector}")
        locator.fill(value)

    def sanitize_dom(self) -> list[dict]:
        stripped = self.page.evaluate(SANITIZE_JS)
        for item in stripped:
            print(f"[DOM-GATE STRIPPED] <{item['tag']}> ({item['reason']}): {item['preview']!r}")
        return stripped

    def safe_text_snapshot(self) -> str:
        self.sanitize_dom()
        return self.page.evaluate("() => document.body.innerText")