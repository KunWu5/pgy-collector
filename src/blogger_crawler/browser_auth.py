from __future__ import annotations

from pathlib import Path
from typing import Callable


class BrowserAutomationUnavailable(RuntimeError):
    pass


class LoginUrlNotConfigured(RuntimeError):
    pass


class LoginTimeout(RuntimeError):
    pass


def _session_path(config: dict[str, dict[str, str]], project_root: Path) -> Path:
    configured_path = config.get("source", {}).get("session_path") or ".session/session.json"
    path = Path(configured_path)
    return path if path.is_absolute() else project_root / path


def _login_url(config: dict[str, dict[str, str]]) -> str:
    login_url = config.get("source", {}).get("login_url", "").strip()
    if not login_url:
        raise LoginUrlNotConfigured(
            "登录地址未配置，请在 config.yaml 的 source.login_url 中填写登录页地址。"
        )
    return login_url


def run_manual_browser_login(
    config: dict[str, dict[str, str]],
    project_root: Path,
    *,
    playwright_factory: Callable[[], object] | None = None,
) -> Path:
    login_url = _login_url(config)
    search_url = config.get("source", {}).get("search_url") or (
        login_url.rstrip("/") + "/dashboard/note/kol"
    )
    session_path = _session_path(config, project_root)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        login_timeout_seconds = int(config.get("source", {}).get("login_timeout_seconds", "300"))
    except ValueError as error:
        raise LoginTimeout("source.login_timeout_seconds 必须是整数秒数。") from error

    if playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserAutomationUnavailable(
                "未安装 Playwright。请先运行: python -m pip install playwright，"
                "再运行: python -m playwright install chromium。"
            ) from error
        playwright_factory = sync_playwright

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url)
            login_trigger = page.get_by_text("登录", exact=True)
            if login_trigger.count() > 0:
                login_trigger.first.click()
            try:
                page.wait_for_function(
                    """
                    () => {
                        const loginForm = document.querySelector('#login-form');
                        const visibleInputs = Array.from(document.querySelectorAll('input'))
                            .filter(input => input.offsetParent !== null);
                        const hasLoginInput = visibleInputs.some(input => {
                            const placeholder = input.getAttribute('placeholder') || '';
                            return placeholder.includes("手机号") || placeholder.includes("验证码");
                        });
                        return !loginForm && !hasLoginInput;
                    }
                    """,
                    timeout=login_timeout_seconds * 1000,
                )
            except Exception as error:
                raise LoginTimeout(
                    f"登录等待超过 {login_timeout_seconds} 秒，请确认已在浏览器中完成登录。"
                ) from error
            try:
                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=login_timeout_seconds * 1000,
                )
                page.wait_for_timeout(min(1500, login_timeout_seconds * 1000))
                if (
                    "/dashboard/" not in page.url
                    or page.get_by_text("账号登录", exact=True).count()
                ):
                    raise LoginTimeout(
                        "登录验证失败：访问搜索页后仍返回登录页，请重新完成登录。"
                    )
            except LoginTimeout:
                raise
            except Exception as error:
                raise LoginTimeout(
                    "登录验证失败：无法打开搜索页，请检查网络后重试。"
                ) from error
            context.storage_state(path=str(session_path))
        finally:
            browser.close()

    return session_path
