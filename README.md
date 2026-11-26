# dom-gate

Deterministic DOM sanitizer and egress firewall for Playwright-based Browser Agents.

## The Problem
Browser agents frequently read raw DOM text (`textContent` or unsanitized accessibility attributes) instead of only what a human sees. Attackers plant invisible payloads (`font-size: 1px`, `opacity: 0`, `left: -9999px`, `color: transparent`, `text-indent: -9999px`, low-contrast text, opaque overlays, HTML comments) to hijack agent navigation and exfiltrate session data.

## How `dom-gate` Works
1. **Pre-Observation Sanitizer:** Walks text nodes, comments, and hidden accessibility attributes (`aria-label`, `alt`, `title`, `placeholder`) and strips content hidden from human sight *before* the agent reads the page—without breaking `<style>`, `<script>`, or visible text inside unclipped wrappers.
2. **Action & Egress Firewall:** Enforces a strict **origin allowlist** (`scheme://host:port`) on `safe_goto()`, `safe_fill()` (blocks sensitive input on untrusted origins or hidden fields), and intercepts all outbound requests at the Playwright **BrowserContext** level (including popups and new tabs).

## Quickstart
```bash
git clone https://github.com/abhinandanpandey-in/dom-gate.git
cd dom-gate
python -m venv venv
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/macOS:
# source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Terminal 1 — Start the local invoice + attacker trap servers:**
```bash
python demo_server.py
```

**Terminal 2 — Run both scenarios:**
```bash
# Scenario 1: Hidden DOM injection (Layer 1 sanitizer strips payloads)
python run_demo.py --mode unprotected --scenario hidden
python run_demo.py --mode protected --scenario hidden

# Scenario 2: Visible injection (Layer 2 firewall blocks unauthorized navigation)
python run_demo.py --mode protected --scenario visible
```

> **Note on the demo agent:** `--provider mock` is a deterministic regex agent included for reproducible local/CI testing (it is **not** an LLM). To test against a real local model, run with Ollama:
> ```bash
> python run_demo.py --mode protected --provider ollama --model llama3.2
> ```

## Run Tests
```bash
pytest -v
```

## What This Does Not Catch
`dom-gate` closes the **hidden-DOM injection path** and enforces **origin-level egress allowlists**, but it is not a complete cure for prompt injection:
* **Visible prompt injections:** Normal readable malicious text is intentionally not stripped (though the Action & Egress Firewall still blocks navigation to untrusted origins).
* **Pure vision (VLM) attacks:** Screenshot-only agents require pixel-level inspection for text baked into images.
* **Same-origin abuse & WebSockets:** Actions targeting an already-allowlisted origin require per-action approval gates, and raw WebSocket frame inspection is not yet implemented.