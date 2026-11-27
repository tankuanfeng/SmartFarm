import sqlite3
import tempfile
import unittest
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

from app import app
from werkzeug.security import check_password_hash


class CsrfTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            attributes = dict(attrs)
            if attributes.get("name") == "csrf_token":
                self.token = attributes.get("value")


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.original_config = {
            key: app.config.get(key)
            for key in (
                "DATABASE",
                "SECRET_KEY",
                "TESTING",
                "WTF_CSRF_ENABLED",
                "WTF_CSRF_TIME_LIMIT",
                "SESSION_COOKIE_SECURE",
            )
        }
        self.temp_dir = tempfile.TemporaryDirectory()
        app.config.update(
            DATABASE=str(Path(self.temp_dir.name) / "users.sqlite3"),
            SECRET_KEY="test-secret-key",
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            WTF_CSRF_TIME_LIMIT=None,
            SESSION_COOKIE_SECURE=False,
        )
        self.client = app.test_client()

    def tearDown(self):
        app.config.update(self.original_config)
        self.temp_dir.cleanup()

    def get_csrf_token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        parser = CsrfTokenParser()
        parser.feed(response.get_data(as_text=True))
        self.assertTrue(parser.token)
        return parser.token

    def register(self, client=None, user_id="farm-owner", email="owner@example.com", password="Farm2026"):
        client = client or self.client
        token = self.get_csrf_token(client, "/register")
        return client.post(
            "/register",
            data={
                "csrf_token": token,
                "user_id": user_id,
                "email": email,
                "password": password,
                "password_confirmation": password,
            },
        )

    def login(self, client, identifier, password="Farm2026"):
        token = self.get_csrf_token(client, "/login")
        return client.post(
            "/login",
            data={
                "csrf_token": token,
                "identifier": identifier,
                "password": password,
            },
        )

    def test_homepage_renders_product_sections_and_auth_links(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("鸡舍环境监测".encode(), response.data)
        self.assertIn("作物产量预测".encode(), response.data)
        self.assertIn(b"/login", response.data)
        self.assertIn(b"/register", response.data)

    def test_registration_hashes_password_and_authenticates_user(self):
        response = self.register(
            user_id="农场主_01",
            email="OWNER@EXAMPLE.COM",
            password="Farm2026",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard")
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        with self.client.session_transaction() as user_session:
            self.assertEqual(user_session["user_id"], "农场主_01")

        with closing(sqlite3.connect(app.config["DATABASE"])) as database:
            user = database.execute(
                "SELECT id, email, password_hash FROM users WHERE id = ?",
                ("农场主_01",),
            ).fetchone()

        self.assertEqual(user[1], "owner@example.com")
        self.assertNotEqual(user[2], "Farm2026")
        self.assertTrue(check_password_hash(user[2], "Farm2026"))
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("主功能正在准备中".encode(), dashboard.data)

    def test_registration_rejects_invalid_email_password_and_confirmation(self):
        cases = (
            ("not-an-email", "Farm2026", "Farm2026", "有效的邮箱"),
            ("owner@example.com", "short7", "short7", "8–64"),
            ("owner@example.com", "1" * 65, "1" * 65, "8–64"),
            ("owner@example.com", "Farm2026!", "Farm2026!", "只能包含"),
            ("owner@example.com", "12345678", "12345678", "必须同时包含"),
            ("owner@example.com", "abcdefgh", "abcdefgh", "必须同时包含"),
            ("owner@example.com", "Farm2026", "Other2026", "不一致"),
        )
        for email, password, confirmation, expected_message in cases:
            with self.subTest(email=email, password=password, confirmation=confirmation):
                token = self.get_csrf_token(self.client, "/register")
                response = self.client.post(
                    "/register",
                    data={
                        "csrf_token": token,
                        "user_id": "farm-owner",
                        "email": email,
                        "password": password,
                        "password_confirmation": confirmation,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected_message.encode(), response.data)

    def test_registration_rejects_duplicate_id_and_email(self):
        self.assertEqual(self.register().status_code, 302)
        other_client = app.test_client()

        duplicate_id = self.register(
            other_client,
            user_id="farm-owner",
            email="another@example.com",
            password="Another2026",
        )
        self.assertEqual(duplicate_id.status_code, 400)
        self.assertIn("用户 ID 已被使用".encode(), duplicate_id.data)

        duplicate_email = self.register(
            other_client,
            user_id="another-owner",
            email="OWNER@example.com",
            password="Another2026",
        )
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertIn("邮箱已被使用".encode(), duplicate_email.data)

    def test_registration_rejects_cross_account_id_email_collision(self):
        self.assertEqual(
            self.register(user_id="id@example.com").status_code,
            302,
        )
        collision = self.register(
            app.test_client(),
            user_id="another-owner",
            email="ID@example.com",
            password="Another2026",
        )

        self.assertEqual(collision.status_code, 400)
        self.assertIn("不能与其他账号重叠".encode(), collision.data)

    def test_login_accepts_user_id_or_email_and_rejects_wrong_password(self):
        self.assertEqual(self.register().status_code, 302)

        by_id = self.login(app.test_client(), "farm-owner")
        self.assertEqual(by_id.status_code, 302)
        self.assertEqual(by_id.headers["Location"], "/dashboard")

        by_email = self.login(app.test_client(), "OWNER@EXAMPLE.COM")
        self.assertEqual(by_email.status_code, 302)
        self.assertEqual(by_email.headers["Location"], "/dashboard")

        wrong_password = self.login(app.test_client(), "farm-owner", "Wrong2026")
        self.assertEqual(wrong_password.status_code, 400)
        self.assertIn("账号或密码不正确".encode(), wrong_password.data)

    def test_dashboard_requires_login_and_logout_clears_session(self):
        anonymous_response = self.client.get("/dashboard")
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertEqual(anonymous_response.headers["Location"], "/login")

        self.assertEqual(self.register().status_code, 302)
        token = self.get_csrf_token(self.client, "/dashboard")
        logout_response = self.client.post("/logout", data={"csrf_token": token})

        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers["Location"], "/login")
        self.assertEqual(self.client.get("/dashboard").headers["Location"], "/login")

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post(
            "/register",
            data={
                "user_id": "farm-owner",
                "email": "owner@example.com",
                "password": "Farm2026",
                "password_confirmation": "Farm2026",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"CSRF", response.data)


if __name__ == "__main__":
    unittest.main()
