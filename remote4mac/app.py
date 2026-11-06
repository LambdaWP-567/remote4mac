import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "services.json"
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
}
SERVICE_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
NOT_FOUND_ERROR = "Not found"


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    url: str


def _parse_service(record: object, existing_ids: Iterable[str]) -> Service:
    if not isinstance(record, dict):
        raise ValueError("Each service must be a JSON object")
    service_id = record.get("id")
    name = record.get("name")
    url = record.get("url")
    if not isinstance(service_id, str) or not SERVICE_ID_PATTERN.fullmatch(service_id):
        raise ValueError("Service IDs may contain lowercase letters, digits, and hyphens")
    if service_id in existing_ids:
        raise ValueError(f"Duplicate service ID: {service_id}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Service {service_id} must have a name")
    if not isinstance(url, str):
        raise ValueError(f"Service {service_id} must have an HTTPS URL")
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError(f"Service {service_id} must have an HTTPS URL")
    return Service(service_id, name.strip(), url)


def load_services(config_path: Path | None = None) -> dict[str, Service]:
    path = config_path or Path(os.environ.get("REMOTE4MAC_CONFIG", DEFAULT_CONFIG))
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Service configuration must be a JSON array")
    services = {}
    for record in records:
        service = _parse_service(record, services.keys())
        services[service.id] = service
    return services


def open_service(service: Service) -> None:
    firefox = os.environ.get("REMOTE4MAC_FIREFOX", "firefox")
    subprocess.Popen(
        [firefox, "--new-tab", service.url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def request_shutdown() -> None:
    subprocess.Popen(
        ["systemctl", "poweroff"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class RemoteHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        static_file = STATIC_FILES.get(path)
        if static_file is None:
            self._send_json(404, {"error": NOT_FOUND_ERROR})
            return
        filename, content_type = static_file
        body = (WEB_ROOT / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "Content-Type must be application/json"})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
        except ValueError:
            self._send_json(400, {"error": "Invalid JSON request"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "JSON request must be an object"})
            return None
        return payload

    def do_GET(self) -> None:
        if self.path in STATIC_FILES:
            self._send_static(self.path)
            return
        if self.path != "/api/services":
            self._send_json(404, {"error": "Not found"})
            return
        try:
            services = load_services()
        except (OSError, ValueError) as error:
            self._send_json(500, {"error": f"Invalid service configuration: {error}"})
            return
        self._send_json(200, [service.__dict__ for service in services.values()])

    def do_POST(self) -> None:
        payload = self._read_json()
        if payload is None:
            return
        if self.path == "/api/shutdown":
            if payload.get("confirm") is not True:
                self._send_json(400, {"error": "Shutdown confirmation required"})
                return
            request_shutdown()
            self._send_json(202, {"status": "shutdown requested"})
            return

        match = re.fullmatch(r"/api/services/([a-z0-9-]+)/open", self.path)
        if match is None:
            self._send_json(404, {"error": NOT_FOUND_ERROR})
            return
        try:
            service = load_services().get(match.group(1))
        except (OSError, ValueError) as error:
            self._send_json(500, {"error": f"Invalid service configuration: {error}"})
            return
        if service is None:
            self._send_json(404, {"error": "Unknown service"})
            return
        open_service(service)
        self._send_json(202, {"status": "service opened", "id": service.id})


class RemoteServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    host = os.environ.get("REMOTE4MAC_HOST", "0.0.0.0")
    port = int(os.environ.get("REMOTE4MAC_PORT", "8765"))
    server = RemoteServer((host, port), RemoteHandler)
    print(f"remote4mac listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()