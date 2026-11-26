# dom-gate

Deterministic DOM sanitization and egress firewall for Browser & Computer-Use Agents (Playwright / CDP).

![dom-gate demo](assets/demo.gif)

## The Problem
Browser agents often read raw DOM text (	extContent / full accessibility trees) instead of only what a human sees. Attackers abuse invisible CSS payloads (ont-size: 1px, opacity: 0, left: -9999px, white-on-white text) to hijack navigation and exfiltrate session data.

## How dom-gate Works
1. **Pre-Observation Sanitizer:** Strips hidden, zero-opacity, micro-font, off-screen, zero-dimension, and low-contrast DOM nodes before the page is serialized for the LLM.
2. **Action & Egress Firewall:** Enforces a strict host allowlist on safe_goto() and intercepts outbound browser requests via Playwright page.route().

## Quickstart
```bash
git clone [https://github.com/abhinandanpandey-in/dom-gate.git](https://github.com/abhinandanpandey-in/dom-gate.git)
cd dom-gate
python -m venv venv
pip install -r requirements.txt
playwright install chromium
```

Start the local invoice + attacker trap servers:
```bash
python demo_server.py
```

Run the attack vs. defense in a second terminal:
```bash
python run_demo.py --mode unprotected
python run_demo.py --mode protected
```

## What This Doesn't Catch
- **Visible prompt injections:** Normal readable malicious text is not stripped (though the egress firewall still blocks untrusted hosts).
- **Pure vision (VLM) attacks:** Screenshot-only agents require pixel-level contrast checks for image-rendered text.
- **Same-origin abuse:** Attacks targeting already-allowlisted domains require per-action approval gates.
