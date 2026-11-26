from urllib.parse import urlparse
from playwright.sync_api import Page, Route

SANITIZE_JS = """
() => {
  const stripped = [];

  function parseRGB(str) {
    const m = str.match(/\\d+(\\.\\d+)?/g);
    return m ? m.map(Number) : [0, 0, 0, 1];
  }

  function colorDistance(c1, c2) {
    return Math.sqrt(
      Math.pow(c1[0] - c2[0], 2) +
      Math.pow(c1[1] - c2[1], 2) +
      Math.pow(c1[2] - c2[2], 2)
    );
  }

  function getEffectiveBg(el) {
    let cur = el;
    while (cur && cur !== document.documentElement) {
      const bg = getComputedStyle(cur).backgroundColor;
      const rgba = parseRGB(bg);
      if (rgba.length < 4 || rgba[3] > 0) return rgba;
      cur = cur.parentElement;
    }
    return [255, 255, 255, 1];
  }

  const elements = Array.from(document.querySelectorAll('body *'));
  for (const el of elements) {
    if (!el.isConnected) continue;
    const text = (el.innerText || el.textContent || '').trim();
    if (!text) continue;

    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    let reason = null;

    if (style.display === 'none' || style.visibility === 'hidden') {
      reason = 'css-hidden';
    } else if (parseFloat(style.opacity) < 0.05) {
      reason = 'zero-opacity';
    } else if (parseFloat(style.fontSize) < 4) {
      reason = 'micro-font';
    } else if (rect.width <= 1 || rect.height <= 1) {
      reason = 'zero-dimensions';
    } else if (rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth + 200) {
      reason = 'off-screen';
    } else {
      const fg = parseRGB(style.color);
      const bg = getEffectiveBg(el);
      if (colorDistance(fg, bg) < 15) {
        reason = 'low-contrast-camo';
      }
    }

    if (reason) {
      stripped.push({
        tag: el.tagName.toLowerCase(),
        reason,
        preview: text.slice(0, 120)
      });
      el.remove();
    }
  }
  return stripped;
}
"""


class DomGateError(Exception):
    pass


class DomGate:
    def __init__(self, page: Page, allowed_hosts: set[str]):
        self.page = page
        self.allowed_hosts = allowed_hosts
        self.blocked_events = []
        self._install_network_gate()

    def _is_allowed(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return host in self.allowed_hosts

    def _install_network_gate(self):
        def handle_route(route: Route):
            url = route.request.url
            if not self._is_allowed(url):
                event = {"type": "BLOCKED_EGRESS", "url": url}
                self.blocked_events.append(event)
                print(f"[DOM-GATE BLOCKED] Unauthorized request: {url}")
                route.abort("blockedbyclient")
                return
            route.continue_()

        self.page.route("**/*", handle_route)

    def safe_goto(self, url: str):
        if not self._is_allowed(url):
            event = {"type": "BLOCKED_NAV", "url": url}
            self.blocked_events.append(event)
            raise DomGateError(f"Blocked navigation to untrusted host: {url}")
        self.page.goto(url, wait_until="networkidle")
        return self.sanitize_dom()

    def sanitize_dom(self) -> list[dict]:
        stripped = self.page.evaluate(SANITIZE_JS)
        for item in stripped:
            print(f"[DOM-GATE STRIPPED] <{item['tag']}> ({item['reason']}): {item['preview']!r}")
        return stripped

    def safe_text_snapshot(self) -> str:
        self.sanitize_dom()
        return self.page.evaluate("() => document.body.innerText")
