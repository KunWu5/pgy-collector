import unittest
from pathlib import Path

from blogger_crawler.collectors import build_collector
from helpers import workspace_tempdir
from blogger_crawler.mock_collector import collect_mock_snapshot
from blogger_crawler.web_collector import SessionNotConfigured


class CollectorSelectionTest(unittest.TestCase):
    def test_build_collector_uses_mock_mode_by_default(self):
        collector = build_collector({})

        self.assertIs(collector, collect_mock_snapshot)

    def test_build_collector_rejects_real_mode_without_saved_session(self):
        config = {
            "run": {"mode": "real"},
            "source": {"session_path": ".session/session.json"},
        }

        with workspace_tempdir() as tmp:
            with self.assertRaisesRegex(SessionNotConfigured, "登录态"):
                build_collector(config, Path(tmp))

    def test_build_collector_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "Unsupported run.mode"):
            build_collector({"run": {"mode": "unknown"}})


if __name__ == "__main__":
    unittest.main()
