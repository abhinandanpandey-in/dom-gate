import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

DEMO_DIR = Path(__file__).parent / "demo"


class InvoiceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DEMO_DIR), **kwargs)

    def log_message(self, format, *args):
        print(f"[INVOICE-SERVER :8000] {args[0]}")


class AttackerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        secret = params.get("secret", ["<none>"])[0]

        print("\n" + "=" * 60)
        print(f"\033[91m[ATTACKER :8080] DATA EXFILTRATED -> secret={secret}\033[0m")
        print("=" * 60 + "\n")

        html = f"""<!DOCTYPE html>
<html>
<body style="background:#140000;color:#ff4d4d;font-family:monospace;padding:48px;">
  <h1>[!] DATA EXFILTRATED</h1>
  <p style="font-size:18px;color:#fff;">Stolen payload received by attacker server:</p>
  <pre style="background:#260000;padding:16px;border:1px solid #ff4d4d;font-size:20px;">secret = {secret}</pre>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def main():
    invoice_srv = HTTPServer(("localhost", 8000), InvoiceHandler)
    attacker_srv = HTTPServer(("127.0.0.1", 8080), AttackerHandler)

    t1 = threading.Thread(target=invoice_srv.serve_forever, daemon=True)
    t2 = threading.Thread(target=attacker_srv.serve_forever, daemon=True)
    t1.start()
    t2.start()

    print("Invoice server running at  http://localhost:8000/invoice.html")
    print("Attacker trap running at   http://127.0.0.1:8080/exfil")
    print("Press Ctrl+C to stop.\n")

    try:
        t1.join()
    except KeyboardInterrupt:
        print("\nShutting down servers.")


if __name__ == "__main__":
    main()

