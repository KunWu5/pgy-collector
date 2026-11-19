import json
import unittest
from pathlib import Path

from helpers import workspace_tempdir
from blogger_crawler.browser_auth import LoginTimeout, run_manual_browser_login


class _FakePage:
    def __init__(self):
        self.visited_url = None
        self.visited_urls = []
        self.url = ""
        self.login_clicked = False
        self.waited_for_login = False
        self.wait_script = ""

    def goto(self, url: str, **kwargs):
        self.visited_url = url
        self.visited_urls.append(url)
        self.url = url

    def get_by_text(self, text: str, *, exact: bool):
        return _FakeLoginTrigger(self)

    def wait_for_function(self, script: str, *, timeout: int):
        self.waited_for_login = True
        self.wait_script = script

    def wait_for_timeout(self, milliseconds: int):
        pass


class _RedirectingPage(_FakePage):
    def goto(self, url: str, **kwargs):
        super().goto(url, **kwargs)
        if "/dashboard/" in url:
            self.url = "https://example.com/"


class _FakeLoginTrigger:
    def __init__(self, page: _FakePage):
        self.page = page

    def count(self):
        return int(len(self.page.visited_urls) == 1)

    @property
    def first(self):
        return self

    def is_visible(self):
        return True

    def click(self):
        self.page.login_clicked = True


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.page = page
        self.saved_path = None

    def new_page(self):
        return self.page

    def storage_state(self, path: str):
        self.saved_path = Path(path)
        self.saved_path.write_text(json.dumps({"cookies": []}), encoding="utf-8")


class _FakeBrowser:
    def __init__(self, context: _FakeContext):
        self.context = context
        self.closed = False

    def new_context(self):
        return self.context

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser):
        self.browser = browser
        self.headless = None

    def launch(self, *, headless: bool):
        self.headless = headless
        return self.browser


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class BrowserAuthTest(unittest.TestCase):
    def test_manual_login_opens_configured_url_and_saves_browser_state(self):
        page = _FakePage()
        context = _FakeContext(page)
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)

        def playwright_factory():
            return _FakePlaywright(chromium)

        config = {
            "source": {
                "login_url": "https://example.test/login",
                "search_url": "https://example.test/dashboard/note/kol",
                "session_path": ".session/session.json",
            }
        }
        with workspace_tempdir() as tmp:
            session_path = run_manual_browser_login(
                config,
                Path(tmp),
                playwright_factory=playwright_factory,
            )

        self.assertEqual(
            page.visited_urls,
            [
                "https://example.test/login",
                "https://example.test/dashboard/note/kol",
            ],
        )
        self.assertTrue(page.login_clicked)
        self.assertTrue(page.waited_for_login)
        self.assertIn('includes("手机号")', page.wait_script)
        self.assertIn('includes("验证码")', page.wait_script)
        self.assertFalse(chromium.headless)
        self.assertTrue(browser.closed)
        self.assertTrue(session_path.exists())
        self.assertEqual(session_path, context.saved_path)

    def test_manual_login_does_not_save_state_when_protected_page_redirects(self):
        page = _RedirectingPage()
        context = _FakeContext(page)
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)

        config = {
            "source": {
                "login_url": "https://example.com/",
                "search_url": "https://example.com/search",
                "session_path": ".session/session.json",
            }
        }
        with workspace_tempdir() as tmp:
            with self.assertRaisesRegex(LoginTimeout, "登录验证失败"):
                run_manual_browser_login(
                    config,
                    Path(tmp),
                    playwright_factory=lambda: _FakePlaywright(chromium),
                )

        self.assertIsNone(context.saved_path)
        self.assertTrue(browser.closed)


if __name__ == "__main__":
    unittest.main()
