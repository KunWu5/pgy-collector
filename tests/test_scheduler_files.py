import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SchedulerFilesTest(unittest.TestCase):
    def run_registration_preview(self, *extra_args):
        path = PROJECT_ROOT / "scripts" / "register_monthly_task.ps1"
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(path),
                *extra_args,
                "-Preview",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_monthly_launcher_checks_runtime_secrets_and_runs_crawl_then_report(self):
        path = PROJECT_ROOT / "scripts" / "run_monthly_crawl.ps1"
        content = path.read_text(encoding="utf-8")

        for marker in [
            "$PSScriptRoot",
            "MYSQL_PASSWORD",
            "PYTHONPATH",
            "session.json",
            "--config",
            "--report",
        ]:
            self.assertIn(marker, content)
        self.assertNotIn("password=", content.lower())
        self.assertNotIn("verification_code", content.lower())

    def test_registration_script_defaults_to_twenty_fifth_day_at_two_am(self):
        path = PROJECT_ROOT / "scripts" / "register_monthly_task.ps1"
        content = path.read_text(encoding="utf-8")
        completed = self.run_registration_preview()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Schedule: day 25 at 02:00", completed.stdout)
        self.assertIn('Triggers.Create(4)', content)
        self.assertIn("$Trigger.DaysOfMonth = $DayMask", content)
        self.assertIn("$Trigger.MonthsOfYear = 4095", content)
        self.assertIn("$Preview", content)
        self.assertNotIn("password=", content.lower())
        self.assertNotIn("verification_code", content.lower())

    def test_registration_preview_reports_next_twenty_fifth_boundary(self):
        completed = self.run_registration_preview("-Day", "25")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(
            completed.stdout,
            r"Next run boundary: \d{4}-\d{2}-25T02:00:00",
        )

    def test_registration_preview_encodes_day_for_windows_com_trigger(self):
        completed = self.run_registration_preview("-Day", "25")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Day mask: 16777216", completed.stdout)


if __name__ == "__main__":
    unittest.main()
