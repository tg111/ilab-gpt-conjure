from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from codex_image.webui.app import create_app
from codex_image.webui.login import (
    LOGIN_REQUIRED_HEADER,
    MAX_FAILED_ATTEMPTS,
    SESSION_COOKIE_MAX_AGE_SECONDS,
    SESSION_COOKIE_NAME,
)


class WebUILoginTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.login_path = self.root / "webui-login.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_app(self):
        return create_app(
            output_root=self.root / "outputs",
            auth_checker=lambda: True,
            auto_start_queue=False,
            require_login=True,
            login_settings_path=self.login_path,
        )

    def test_unauthenticated_requests_are_gated(self) -> None:
        client = TestClient(self.make_app())

        api = client.get("/api/queue")
        self.assertEqual(api.status_code, 401)
        self.assertEqual(api.headers[LOGIN_REQUIRED_HEADER], "required")
        self.assertEqual(api.json(), {"detail": "login_required"})

        for path in ("/", "/history"):
            page = client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn('id="loginForm"', page.text)
            self.assertEqual(page.headers[LOGIN_REQUIRED_HEADER], "required")

        self.assertEqual(client.get("/static/login.html").status_code, 200)
        self.assertEqual(client.get("/api/login/status").json(), {
            "configured": False,
            "authenticated": False,
            "setup_allowed": True,
        })

    def test_first_visit_sets_any_password_and_signs_in(self) -> None:
        client = TestClient(self.make_app())

        self.assertEqual(client.post("/api/login", json={"password": "x"}).status_code, 409)
        setup = client.post("/api/login/setup", json={"password": "1"})
        self.assertEqual(setup.status_code, 200)

        cookie = setup.headers["set-cookie"]
        self.assertIn(f"{SESSION_COOKIE_NAME}=", cookie)
        self.assertIn(f"Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)

        self.assertEqual(client.get("/api/queue").status_code, 200)
        index = client.get("/")
        self.assertNotIn('id="loginForm"', index.text)
        self.assertIn(f"Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}", index.headers["set-cookie"])

        stored = json.loads(self.login_path.read_text(encoding="utf-8"))
        self.assertNotIn('"1"', json.dumps(stored))
        self.assertEqual(len(stored["sessions"]), 1)

        # A second setup cannot replace the password.
        other = TestClient(self.make_app())
        self.assertEqual(other.post("/api/login/setup", json={"password": "2"}).status_code, 409)

    def test_session_survives_server_restart(self) -> None:
        first = TestClient(self.make_app())
        first.post("/api/login/setup", json={"password": "pw"})
        token = first.cookies.get(SESSION_COOKIE_NAME)

        restarted = TestClient(self.make_app())
        restarted.cookies.set(SESSION_COOKIE_NAME, token)
        self.assertEqual(restarted.get("/api/queue").status_code, 200)

    def test_login_logout_and_wrong_password(self) -> None:
        TestClient(self.make_app()).post("/api/login/setup", json={"password": "secret"})
        client = TestClient(self.make_app())

        self.assertEqual(client.post("/api/login", json={"password": ""}).status_code, 400)
        wrong = client.post("/api/login", json={"password": "nope"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), {"detail": "wrong_password"})

        self.assertEqual(client.post("/api/login", json={"password": "secret"}).status_code, 200)
        self.assertEqual(client.get("/api/queue").status_code, 200)
        self.assertEqual(client.get("/login", follow_redirects=False).status_code, 303)

        token = client.cookies.get(SESSION_COOKIE_NAME)
        self.assertEqual(client.post("/api/logout").status_code, 200)
        client.cookies.set(SESSION_COOKIE_NAME, token)
        self.assertEqual(client.get("/api/queue").status_code, 401)

    def test_repeated_wrong_passwords_are_throttled(self) -> None:
        client = TestClient(self.make_app())
        client.post("/api/login/setup", json={"password": "secret"})
        client.cookies.clear()
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.assertEqual(client.post("/api/login", json={"password": "bad"}).status_code, 401)
        self.assertEqual(client.post("/api/login", json={"password": "secret"}).status_code, 429)

    def test_setup_is_limited_to_this_device(self) -> None:
        app = self.make_app()
        app.state.lan_access.enabled = True
        app.state.lan_access.host = "0.0.0.0"
        remote = TestClient(app, base_url="http://10.0.0.5", client=("192.168.1.20", 50000))

        self.assertFalse(remote.get("/api/login/status").json()["setup_allowed"])
        blocked = remote.post("/api/login/setup", json={"password": "pw"})
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(self.login_path.exists())

    def test_login_is_off_unless_requested(self) -> None:
        app = create_app(output_root=self.root / "outputs", auth_checker=lambda: True, auto_start_queue=False)
        self.assertEqual(TestClient(app).get("/api/queue").status_code, 200)


if __name__ == "__main__":
    unittest.main()
