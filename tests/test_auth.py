import json
import unittest
from pathlib import Path

from helpers import workspace_tempdir
from blogger_crawler.auth import prepare_login_session
from blogger_crawler.web_collector import CollectorNotConfigured


class AuthTest(unittest.TestCase):
    def test_prepare_login_session_requires_account(self):
        with workspace_tempdir() as tmp:
            with self.assertRaisesRegex(CollectorNotConfigured, "采集账号未配置"):
                prepare_login_session({"source": {"username": "", "password": ""}}, Path(tmp), "123456")

    def test_prepare_login_session_writes_placeholder_without_secrets(self):
        config = {
            "source": {
                "username": "demo_user",
                "password": "demo_password",
                "session_path": ".test_tmp/source_session.json",
            }
        }
        with workspace_tempdir() as tmp:
            session_path = prepare_login_session(config, Path(tmp), "123456")
            session = json.loads(session_path.read_text(encoding="utf-8"))

        self.assertEqual(session["username"], "demo_user")
        self.assertEqual(session["status"], "verification_code_collected")
        self.assertEqual(session["next_step"], "implement_browser_login")
        self.assertNotIn("demo_password", session_path.read_text(encoding="utf-8"))
        self.assertNotIn("123456", session_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
