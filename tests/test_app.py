import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from remote4mac.app import (
    RemoteHandler,
    RemoteServer,
    Service,
    load_services,
    open_service,
    request_shutdown,
)


class ServiceConfigTests(unittest.TestCase):
    def test_loads_configured_services(self):
        services = load_services(Path(__file__).parent.parent / "config" / "services.json")

        self.assertEqual(list(services), ["netflix", "prime-video", "ard", "joyn"])
        self.assertEqual(services["netflix"].url, "https://www.netflix.com/")

    def test_rejects_non_https_service_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "services.json"
            config_path.write_text(
                json.dumps([{"id": "bad", "name": "Bad", "url": "http://example.com"}]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "HTTPS"):
                load_services(config_path)

    def test_rejects_duplicate_service_ids(self):
        service = {"id": "same", "name": "Same", "url": "https://example.com"}
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "services.json"
            config_path.write_text(json.dumps([service, service]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_services(config_path)


class HostActionTests(unittest.TestCase):
    @patch("remote4mac.app.subprocess.Popen")
    def test_opens_only_the_configured_service_url(self, popen):
        service = Service("netflix", "Netflix", "https://www.netflix.com/")

        open_service(service)

        self.assertEqual(popen.call_args.args[0], ["firefox", "--new-tab", service.url])

    @patch("remote4mac.app.subprocess.Popen")
    def test_requests_shutdown_without_running_it_in_the_test(self, popen):
        request_shutdown()

        self.assertEqual(popen.call_args.args[0], ["systemctl", "poweroff"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"REMOTE4MAC_CONFIG": str(
            Path(__file__).parent.parent / "config" / "services.json"
        )})
        self.environment.start()
        self.server = RemoteServer(("127.0.0.1", 0), RemoteHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.environment.stop()

    def request(self, method, path, payload=None, content_type="application/json"):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": content_type} if body is not None else {}
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        return response.status, response.read()

    def test_home_serves_the_remote_ui(self):
        status, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        self.assertIn(b"Streaming<br>", body)
        self.assertIn(b"starten.", body)

    @patch("remote4mac.app.open_service")
    def test_open_route_only_accepts_configured_service_ids(self, open_service_mock):
        status, body = self.request("POST", "/api/services/netflix/open", {})

        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["id"], "netflix")
        open_service_mock.assert_called_once()

        status, _ = self.request("POST", "/api/services/unknown/open", {})

        self.assertEqual(status, 404)

    @patch("remote4mac.app.request_shutdown")
    def test_shutdown_route_requires_explicit_confirmation(self, shutdown_mock):
        status, _ = self.request("POST", "/api/shutdown", {"confirm": False})

        self.assertEqual(status, 400)
        shutdown_mock.assert_not_called()

        status, _ = self.request("POST", "/api/shutdown", {"confirm": True})

        self.assertEqual(status, 202)
        shutdown_mock.assert_called_once()

    def test_mutating_routes_reject_form_submissions(self):
        status, _ = self.request(
            "POST",
            "/api/shutdown",
            {"confirm": True},
            content_type="application/x-www-form-urlencoded",
        )

        self.assertEqual(status, 415)


if __name__ == "__main__":
    unittest.main()