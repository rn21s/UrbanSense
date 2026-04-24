from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from app.simulation import run_product_simulation
from app.data import scenario_payload
from app.env import load_env
from app.grab_maps import grab_map_asset, locality_insights, map_style, search_places
from app.onemap import locality_route, resolve_locality_places, route_matrix, warm_locality_cache


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
        parsed = urlparse(self.path)
        if parsed.path == "/api/scenario":
            self._json(scenario_payload())
            return
        if parsed.path == "/api/onemap/places":
            self._json({"places": resolve_locality_places()})
            return
        if parsed.path == "/api/onemap/routes":
            self._json(route_matrix())
            return
        if parsed.path == "/api/onemap/cache":
            self._json(warm_locality_cache())
            return
        if parsed.path == "/api/grab/search":
            query = parse_qs(parsed.query)
            keyword = _query_value(query, "keyword")
            limit = _query_value(query, "limit") or 8
            self._json(search_places(keyword, limit=limit))
            return
        if parsed.path == "/api/grab/style.json":
            try:
                self._json(map_style())
            except (RuntimeError, HTTPError, URLError) as exc:
                self.send_error(503, str(exc))
            return
        if parsed.path.startswith("/api/grab/vector/"):
            self._grab_asset(parsed.path.removeprefix("/api/grab/"))
            return
        if parsed.path.startswith("/api/grab/fonts/"):
            self._grab_asset(parsed.path.removeprefix("/api/grab/"))
            return
        if parsed.path.startswith("/api/grab/styles/"):
            self._grab_asset(parsed.path.removeprefix("/api/grab/"))
            return
        if parsed.path == "/api/onemap/route":
            query = parse_qs(parsed.query)
            origin = _query_value(query, "origin")
            destination = _query_value(query, "destination")
            mode = _query_value(query, "mode") or "walk"
            if not origin or not destination:
                self.send_error(400, "origin and destination are required")
                return
            try:
                self._json(locality_route(origin, destination, mode))
            except Exception as exc:
                self.send_error(502, str(exc))
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
            "notes": payload.get("notes", ""),
        }
        location = payload.get("location") if isinstance(payload.get("location"), dict) else None
        locality = None
        if location and location.get("lat") and location.get("lng"):
            locality = locality_insights(location["lat"], location["lng"], product=product, radius_km=1.0)
        self._json(run_product_simulation(
            product,
            agent_count=_agent_count(payload.get("agent_count")),
            selected_persona_ids=_selected_persona_ids(payload.get("selected_persona_ids")),
            locality=locality,
        ))

    def _json(self, payload):
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _grab_asset(self, asset_path):
        try:
            asset = grab_map_asset(asset_path)
        except HTTPError as exc:
            self.send_error(exc.code, "Grab Maps upstream error")
            return
        except (RuntimeError, URLError) as exc:
            self.send_error(503, str(exc))
            return

        body = asset["body"]
        self.send_response(200)
        self.send_header("content-type", asset["content_type"])
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    load_env()
    port = _available_port(8000)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"UrbanSense AI running at http://localhost:{port}")
    server.serve_forever()


def _available_port(start):
    for port in range(start, start + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available localhost port from 8000 to 8009.")


def _query_value(query, key):
    values = query.get(key)
    return values[0] if values else None


def _agent_count(value):
    try:
        return max(1, min(11, int(value)))
    except (TypeError, ValueError):
        return None


def _selected_persona_ids(value):
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)]


if __name__ == "__main__":
    main()
