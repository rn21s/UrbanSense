from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from app.simulation import run_product_simulation
from app.data import scenario_payload


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path)
        clean_path = parsed.path
        if clean_path == "/":
            clean_path = "/index.html"
        return str(STATIC_DIR / clean_path.lstrip("/"))

    def do_GET(self):
        if self.path == "/api/scenario":
            self._json(scenario_payload())
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/simulate":
            self.send_error(404, "Unknown endpoint")
            return

        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        product = {
            "name": payload.get("name", "Paracetamol 500mg"),
            "category": payload.get("category", "medicine"),
            "price_sgd": float(payload.get("price_sgd", 4.90)),
            "notes": payload.get("notes", "Over-the-counter pain and fever relief"),
        }
        self._json(run_product_simulation(product))

    def _json(self, payload):
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Shell Select POC running at http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()

