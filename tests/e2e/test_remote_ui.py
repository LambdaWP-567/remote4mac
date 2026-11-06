import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from remote4mac.app import RemoteHandler, RemoteServer


class WaitingTestSubprocess:
    def __getattr__(self, name):
        return getattr(subprocess, name)

    def Popen(self, args, **kwargs):
        process = subprocess.Popen(args, **kwargs)
        if args and args[0] == os.environ["REMOTE4MAC_FIREFOX"]:
            process.wait(timeout=5)
        return process


class QuietRemoteHandler(RemoteHandler):
    def log_message(self, format, *args):
        pass


class RemoteUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(cls.temp_directory.name)
        cls.launch_log = temporary_path / "firefox-launches.jsonl"
        fake_firefox = temporary_path / "fake-firefox"
        fake_firefox.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['REMOTE4MAC_TEST_LAUNCH_LOG'], 'a', encoding='utf-8') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n",
            encoding="utf-8",
        )
        fake_firefox.chmod(0o755)

        config_path = Path(__file__).resolve().parents[2] / "config" / "services.json"
        cls.services = json.loads(config_path.read_text(encoding="utf-8"))
        cls.environment = patch.dict(
            os.environ,
            {
                "REMOTE4MAC_CONFIG": str(config_path),
                "REMOTE4MAC_FIREFOX": str(fake_firefox),
                "REMOTE4MAC_TEST_LAUNCH_LOG": str(cls.launch_log),
            },
        )
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.addClassCleanup(cls.temp_directory.cleanup)

        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.firefox.launch()
        cls.addClassCleanup(cls.browser.close)

        cls.subprocess_patcher = patch(
            "remote4mac.app.subprocess", WaitingTestSubprocess()
        )
        cls.subprocess_patcher.start()
        cls.addClassCleanup(cls.subprocess_patcher.stop)

        cls.server = RemoteServer(("127.0.0.1", 0), QuietRemoteHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server_thread.join)
        cls.addClassCleanup(cls.server.shutdown)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.goto(self.base_url, wait_until="networkidle")

    def test_service_buttons_request_firefox_and_show_the_latest_service(self):
        expect(self.page.locator("#connection-label")).to_have_text("Verbunden")
        buttons = self.page.get_by_role(
            "button", name=re.compile(r".* auf dem Bildschirm öffnen")
        )
        self.assertEqual(buttons.count(), len(self.services))

        launches = []
        for service in self.services:
            button = self.page.get_by_role(
                "button", name=f"{service['name']} auf dem Bildschirm öffnen"
            )
            self.assertEqual(button.count(), 1)
            with self.page.expect_response(
                lambda response, service_id=service["id"]:
                response.request.method == "POST"
                and response.url.endswith(f"/api/services/{service_id}/open")
            ) as response_info:
                button.click()

            self.assertEqual(response_info.value.status, 202)
            expect(button).to_have_attribute("aria-pressed", "true")
            expect(button.locator(".service-status")).to_have_text(
                "Zuletzt an Firefox übergeben"
            )
            expect(self.page.locator(".service-button[aria-pressed='true']")).to_have_count(1)
            expect(self.page.locator("#message")).to_have_text(
                f"{service['name']} wurde an Firefox übergeben."
            )

            launches.append(["--new-tab", service["url"]])
            deadline = time.monotonic() + 5
            recorded = []
            while time.monotonic() < deadline:
                if self.launch_log.exists():
                    recorded = [
                        json.loads(line)
                        for line in self.launch_log.read_text(encoding="utf-8").splitlines()
                    ]
                    if len(recorded) >= len(launches):
                        break
                time.sleep(0.02)
            self.assertEqual(recorded, launches)

        shutdown_requests = []
        self.page.on(
            "request",
            lambda request: shutdown_requests.append(request.url)
            if request.url.endswith("/api/shutdown")
            else None,
        )
        self.page.evaluate("window.confirm = () => false")
        self.page.get_by_role("button", name="Server ausschalten").click()
        self.assertEqual(shutdown_requests, [])


if __name__ == "__main__":
    unittest.main()