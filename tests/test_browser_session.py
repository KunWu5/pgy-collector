import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import workspace_tempdir
from blogger_crawler.models import Blogger
from blogger_crawler.browser_session import BrowserSession


class FakeContext:
    def __init__(self):
        self.close_count = 0

    def close(self):
        self.close_count += 1


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()
        self.new_context_calls = 0
        self.close_count = 0

    def new_context(self, **kwargs):
        self.new_context_calls += 1
        self.storage_state = kwargs["storage_state"]
        return self.context

    def close(self):
        self.close_count += 1


class FakeChromium:
    def __init__(self, browser):
        self.browser = browser
        self.launch_calls = 0

    def launch(self, **kwargs):
        self.launch_calls += 1
        self.headless = kwargs["headless"]
        return self.browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


class FakePlaywrightManager:
    def __init__(self, playwright):
        self.playwright = playwright
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self.playwright

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1


class BrowserSessionTest(unittest.TestCase):
    def test_reuses_one_browser_and_context_for_multiple_bloggers(self):
        with workspace_tempdir() as tmp:
            session_path = Path(tmp) / "session.json"
            session_path.write_text("{}", encoding="utf-8")
            browser = FakeBrowser()
            playwright = FakePlaywright(browser)
            manager = FakePlaywrightManager(playwright)
            config = {"source": {"session_path": str(session_path)}}

            with patch(
                "blogger_crawler.browser_session.collect_snapshot_in_context",
                side_effect=lambda context, blogger, crawl_month, config, project_root, **kwargs: (
                    blogger.red_id,
                    crawl_month,
                ),
            ) as collect:
                with BrowserSession(
                    config,
                    Path(tmp),
                    playwright_factory=lambda: manager,
                ) as session:
                    first = session.collect(Blogger("one"), "2026-08")
                    second = session.collect(Blogger("two"), "2026-08")

        self.assertEqual(first, ("one", "2026-08"))
        self.assertEqual(second, ("two", "2026-08"))
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(playwright.chromium.launch_calls, 1)
        self.assertEqual(browser.new_context_calls, 1)
        self.assertEqual(browser.context.close_count, 1)
        self.assertEqual(browser.close_count, 1)
        self.assertEqual(manager.enter_count, 1)
        self.assertEqual(manager.exit_count, 1)


if __name__ == "__main__":
    unittest.main()
