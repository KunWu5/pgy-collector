from __future__ import annotations

from pathlib import Path
from typing import Callable

from .browser_auth import BrowserAutomationUnavailable
from .models import Blogger, Snapshot
from .web_collector import (
    collect_snapshot_in_context,
    validate_session,
)


class BrowserSession:
    """Own one Playwright browser/context for a complete blogger batch."""

    def __init__(
        self,
        config: dict[str, dict[str, str]],
        project_root: Path,
        *,
        playwright_factory: Callable[[], object] | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.playwright_factory = playwright_factory
        self._playwright_manager = None
        self._playwright = None
        self.browser = None
        self.context = None
        self.search_url = ""
        self.timeout_ms = 30_000

    def __enter__(self) -> "BrowserSession":
        source_config = self.config.get("source", {})
        session_path = validate_session(source_config, self.project_root)
        login_url = source_config.get("login_url", "https://example.com/").strip()
        self.search_url = source_config.get("search_url") or (
            login_url.rstrip("/") + "/dashboard/note/kol"
        )
        try:
            self.timeout_ms = int(source_config.get("request_timeout_ms", "30000"))
        except ValueError:
            self.timeout_ms = 30_000

        factory = self.playwright_factory
        if factory is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as error:
                raise BrowserAutomationUnavailable(
                    "未安装 Playwright。请先运行: python -m pip install -r requirements.txt，"
                    "再运行: python -m playwright install chromium。"
                ) from error
            factory = sync_playwright

        self._playwright_manager = factory()
        try:
            self._playwright = self._playwright_manager.__enter__()
            self.browser = self._playwright.chromium.launch(headless=True)
            self.context = self.browser.new_context(storage_state=str(session_path))
        except Exception:
            self.close()
            raise
        return self

    def collect(self, blogger: Blogger, crawl_month: str) -> Snapshot:
        if self.context is None:
            raise RuntimeError("BrowserSession must be entered before collecting.")
        return collect_snapshot_in_context(
            self.context,
            blogger,
            crawl_month,
            self.config,
            self.project_root,
            search_url=self.search_url,
            timeout_ms=self.timeout_ms,
        )

    def __call__(self, blogger: Blogger, crawl_month: str) -> Snapshot:
        return self.collect(blogger, crawl_month)

    def close(self) -> None:
        context, browser, manager = self.context, self.browser, self._playwright_manager
        self.context = None
        self.browser = None
        self._playwright_manager = None
        try:
            if context is not None:
                context.close()
        finally:
            try:
                if browser is not None:
                    browser.close()
            finally:
                if manager is not None:
                    manager.__exit__(None, None, None)

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.close()
        return False
