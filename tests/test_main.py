import io
import os
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from helpers import workspace_tempdir
from blogger_crawler.main import (
    build_parser,
    export_filename,
    load_config,
    log_filename,
    main,
    run,
    run_login,
)
from blogger_crawler.models import Blogger


class MainTest(unittest.TestCase):
    def test_resume_and_retry_failed_flags_are_mutually_exclusive(self):
        parser = build_parser()

        resume_args = parser.parse_args(["--resume"])
        retry_args = parser.parse_args(["--retry-failed"])

        self.assertTrue(resume_args.resume)
        self.assertTrue(retry_args.retry_failed)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--resume", "--retry-failed"])

    def test_export_filename_marks_real_real_results(self):
        self.assertEqual(export_filename("2026-07", "real"), "2026-07_real_result.xlsx")
        self.assertEqual(export_filename("2026-07", "mock"), "2026-07_mock_result.xlsx")

    def test_report_flag_is_an_exclusive_action(self):
        parser = build_parser()

        report_args = parser.parse_args(["--report", "--month", "2026-08"])

        self.assertTrue(report_args.report)
        self.assertEqual(report_args.month, "2026-08")

    def test_log_filename_separates_real_and_mock_runs(self):
        self.assertEqual(log_filename("2026-07", "real"), "2026-07_real_run.log")
        self.assertEqual(log_filename("2026-07", "mock"), "2026-07_mock_run.log")

    def test_load_config_resolves_mysql_password_from_environment(self):
        with patch(
            "blogger_crawler.main.load_simple_yaml",
            return_value={"mysql": {"password_env": "MYSQL_PASSWORD"}},
        ):
            with patch.dict(os.environ, {"MYSQL_PASSWORD": "runtime-value"}):
                _, config = load_config("config.yaml")

        self.assertEqual(config["mysql"]["password"], "runtime-value")

    def test_dry_run_does_not_require_mysql_password_environment_variable(self):
        config = {
            "mysql": {"password_env": "MYSQL_PASSWORD"},
            "input": {"blogger_list": "data/blogger_list.xlsx"},
            "output": {"export_dir": "exports", "log_dir": "logs"},
            "run": {"mode": "mock", "crawl_month": "2026-08"},
        }
        with patch("blogger_crawler.main.load_simple_yaml", return_value=config):
            with patch("blogger_crawler.main.load_bloggers", return_value=[]):
                with patch("blogger_crawler.main.build_collector"):
                    with patch("blogger_crawler.main.collect_snapshots", return_value=[]):
                        with patch("blogger_crawler.main.export_snapshots", return_value=0):
                            with patch.dict(os.environ, {"MYSQL_PASSWORD": ""}):
                                exit_code = run("config.yaml", dry_run=True, month="2026-08")

        self.assertEqual(exit_code, 0)

    def test_login_does_not_require_mysql_password_environment_variable(self):
        config = {
            "mysql": {"password_env": "MYSQL_PASSWORD"},
            "source": {"login_url": "https://example.test/login"},
        }
        session_path = Path("session.json")
        with patch("blogger_crawler.main.load_simple_yaml", return_value=config):
            with patch(
                "blogger_crawler.main.run_manual_browser_login",
                return_value=session_path,
            ):
                with patch.dict(os.environ, {"MYSQL_PASSWORD": ""}):
                    exit_code = run_login("config.yaml")

        self.assertEqual(exit_code, 0)

    def test_missing_mysql_secret_prints_friendly_error(self):
        config = {
            "mysql": {"password_env": "MYSQL_PASSWORD"},
            "input": {"blogger_list": "data/blogger_list.xlsx"},
            "output": {"export_dir": "exports", "log_dir": "logs"},
            "run": {"mode": "mock", "crawl_month": "2026-08"},
        }
        stderr = io.StringIO()
        with patch("blogger_crawler.main.load_simple_yaml", return_value=config):
            with patch.dict(os.environ, {"MYSQL_PASSWORD": ""}):
                with redirect_stderr(stderr):
                    exit_code = main(["--config", "config.yaml"])

        self.assertEqual(exit_code, 2)
        self.assertIn("MYSQL_PASSWORD", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_real_mode_without_saved_session_prints_friendly_error(self):
        with workspace_tempdir() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                "mysql:\n"
                "  host: localhost\n"
                "  port: 3306\n"
                "  database: blogger_data\n"
                "  user: blogger_user\n"
                "  password: test123456\n"
                "input:\n"
                "  blogger_list: data/blogger_list.xlsx\n"
                "output:\n"
                "  export_dir: exports\n"
                "  log_dir: logs\n"
                "run:\n"
                "  crawl_month: 2026-07\n"
                "  mode: real\n"
                "source:\n"
                f"  session_path: {Path(tmp) / 'missing-session.json'}\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with patch(
                "blogger_crawler.main.load_bloggers",
                return_value=[Blogger("10001", "Mock-A")],
            ):
                with redirect_stderr(stderr):
                    exit_code = main(["--config", str(config_path), "--dry-run"])

        self.assertEqual(exit_code, 2)
        self.assertIn("登录态", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_login_command_saves_browser_session_without_running_crawl(self):
        with workspace_tempdir() as tmp:
            config_path = Path(tmp) / "config.yaml"
            session_path = Path(tmp) / "session.json"
            config_path.write_text(
                "mysql:\n"
                "  host: localhost\n"
                "  port: 3306\n"
                "  database: blogger_data\n"
                "  user: blogger_user\n"
                "  password: test123456\n"
                "input:\n"
                "  blogger_list: data/blogger_list.xlsx\n"
                "output:\n"
                "  export_dir: exports\n"
                "  log_dir: logs\n"
                "run:\n"
                "  crawl_month: 2026-07\n"
                "  mode: real\n"
                "source:\n"
                "  login_url: https://example.test/login\n"
                f"  session_path: {session_path}\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with patch("blogger_crawler.main.run_manual_browser_login", return_value=session_path):
                with redirect_stdout(stdout):
                    exit_code = main(["--config", str(config_path), "--login"])

        self.assertEqual(exit_code, 0)
        self.assertIn(str(session_path), stdout.getvalue())

    def test_reset_month_requires_explicit_confirmation(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["--reset-month", "2026-08"])

        self.assertEqual(exit_code, 2)
        self.assertIn("--yes", stderr.getvalue())

    def test_backup_command_uses_backup_action_without_running_crawl(self):
        with patch("blogger_crawler.main.run_backup", return_value=0) as backup:
            exit_code = main(["--backup", "--config", "config.yaml"])

        self.assertEqual(exit_code, 0)
        backup.assert_called_once_with("config.yaml")


if __name__ == "__main__":
    unittest.main()
