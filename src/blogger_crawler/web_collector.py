from __future__ import annotations

from datetime import datetime
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .browser_auth import BrowserAutomationUnavailable
from .models import Blogger, Snapshot
from .selectors import (
    DETAIL_RESULT_ROW,
    NOTES_RATE_API_PATH,
    PERIOD_DROPDOWN,
    PERIOD_OPTION,
    PROTECTED_PATH_PREFIX,
    SEARCH_API_PATH,
    SEARCH_TYPE_TAB,
)


class CollectorNotConfigured(RuntimeError):
    pass


class SessionNotConfigured(CollectorNotConfigured):
    pass


class SessionExpired(CollectorNotConfigured):
    pass


class CollectorDataError(RuntimeError):
    pass


def validate_source_config(source_config: dict[str, str] | None) -> None:
    username = (source_config or {}).get("username", "").strip()
    password = (source_config or {}).get("password", "").strip()
    if not username or not password:
        raise CollectorNotConfigured(
            "采集账号未配置。请继续使用 run.mode: mock，或在 config.yaml 的 source.username / source.password 填写账号后再切换到 run.mode: real。"
        )


def _session_path(source_config: dict[str, str], project_root: Path) -> Path:
    configured_path = source_config.get("session_path") or ".session/session.json"
    path = Path(configured_path)
    return path if path.is_absolute() else project_root / path


def validate_session(source_config: dict[str, str] | None, project_root: Path) -> Path:
    config = source_config or {}
    path = _session_path(config, project_root)
    if not path.exists() or path.stat().st_size == 0:
        raise SessionNotConfigured(
            f"登录态不存在：{path}。请先运行 python src/main.py --login 完成登录。"
        )
    return path


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if text.endswith(("w", "W")):
        return int(float(text[:-1]) * 10_000)
    try:
        return int(float(text))
    except ValueError:
        return default


def _as_decimal(value: Any, default: str = "0.00") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(default)


def _append_unique(values: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip() and value.strip() not in values:
        values.append(value.strip())


def _extract_tags(kol: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for category in kol.get("contentTags") or []:
        if not isinstance(category, dict):
            continue
        _append_unique(tags, category.get("taxonomy1Tag"))
        for tag in category.get("taxonomy2Tags") or []:
            _append_unique(tags, tag)
    for key in ("personalTags", "featureTags"):
        for tag in kol.get(key) or []:
            _append_unique(tags, tag)
    return tags


def _find_matching_kol(kols: list[dict[str, Any]], blogger: Blogger) -> dict[str, Any]:
    red_id = str(blogger.red_id).strip()
    for kol in kols:
        if str(kol.get("redId", "")).strip() == red_id:
            return kol
    nickname = (blogger.nickname or "").strip()
    for kol in kols:
        if nickname and str(kol.get("name", "")).strip() == nickname:
            return kol
    raise CollectorDataError(
        f"搜索结果未匹配博主：{blogger.nickname or blogger.red_id}（{blogger.red_id}）。"
    )


def select_search_payload(
    payloads: list[dict[str, Any]],
    blogger: Blogger,
) -> dict[str, Any]:
    for payload in reversed(payloads):
        if not payload.get("success"):
            continue
        kols = (payload.get("data") or {}).get("kols") or []
        if isinstance(kols, list):
            try:
                _find_matching_kol(kols, blogger)
                return payload
            except CollectorDataError:
                continue
    raise CollectorDataError(
        f"搜索结果未匹配博主：{blogger.nickname or blogger.red_id}（{blogger.red_id}）。"
    )


def parse_snapshot(
    payload: dict[str, Any],
    blogger: Blogger,
    crawl_month: str,
) -> Snapshot:
    if not payload.get("success"):
        raise CollectorDataError(f"搜索接口返回失败：{payload.get('msg') or 'unknown error'}")
    data = payload.get("data") or {}
    kols = data.get("kols") or []
    if not isinstance(kols, list) or not kols:
        raise CollectorDataError(f"未找到博主：{blogger.nickname or blogger.red_id}。")
    kol = _find_matching_kol(kols, blogger)

    return Snapshot(
        red_id=str(kol.get("redId") or blogger.red_id),
        crawl_month=crawl_month,
        nickname=str(kol.get("name") or blogger.nickname or blogger.red_id),
        fans_count=_as_int(kol.get("fansNum"), _as_int(kol.get("fansCount"))),
        image_price=_as_decimal(kol.get("picturePrice"), str(kol.get("lowerPrice") or "0")),
        video_price=_as_decimal(kol.get("videoPrice"), str(kol.get("lowerPrice") or "0")),
        tags=_extract_tags(kol),
        note_count_30d=_as_int(kol.get("coopNoteNum30d")),
        exposure_median_30d=_as_int(kol.get("accumCommonImpMedinNum30d")),
        read_median_30d=_as_int(kol.get("clickMidNum")),
        interaction_median_30d=_as_int(kol.get("mEngagementNum")),
        note_count_90d=None,
        exposure_median_90d=None,
        read_median_90d=None,
        interaction_median_90d=None,
        crawl_status="success",
        error_message=None,
        crawled_at=datetime.now(),
    )


def parse_detail_metrics(payload: dict[str, Any]) -> dict[str, int]:
    """Parse the cooperation metrics shown in a blogger's detail page."""
    if not payload.get("success"):
        raise CollectorDataError(
            f"详情指标接口返回失败：{payload.get('msg') or 'unknown error'}"
        )
    data = payload.get("data") or {}
    return {
        "note_count": _as_int(data.get("noteNumber")),
        "exposure_median": _as_int(data.get("impMedian")),
        "read_median": _as_int(data.get("readMedian")),
        "interaction_median": _as_int(
            data.get("mEngagementNum"),
        ),
    }


def prepare_search_page(page: Any, timeout_ms: int) -> Any:
    page.wait_for_timeout(min(1500, timeout_ms))
    current_url = getattr(page, "url", "")
    if current_url and PROTECTED_PATH_PREFIX not in current_url:
        raise SessionExpired("登录态已失效，请重新运行 --login。")
    try:
        tabs = page.locator(SEARCH_TYPE_TAB)
        if tabs.count() >= 2:
            tabs.nth(1).click()
        inputs = page.locator("input")
        for index in range(inputs.count()):
            placeholder = inputs.nth(index).get_attribute("placeholder") or ""
            if "博主昵称" in placeholder:
                return inputs.nth(index)
    except AttributeError:
        tabs = page.get_by_text("搜昵称", exact=True)
        if tabs.count() > 0:
            tabs.first.click()
        return page.get_by_placeholder("按博主昵称/博主ID找博主")
    raise CollectorDataError("搜索框未加载。")


def select_detail_period(page: Any, days: int) -> None:
    if days not in (30, 90):
        raise ValueError("详情页时间范围只支持30或90日。")
    target = f"近{days}日"
    wrappers = page.locator(PERIOD_DROPDOWN)
    matching_wrappers = [
        index
        for index, text in enumerate(wrappers.all_inner_texts())
        if text.strip() in ("近30日", "近90日")
    ]
    if not matching_wrappers:
        raise CollectorDataError(f"详情页未找到时间筛选：{target}。")
    wrappers.nth(matching_wrappers[0]).click()

    options = page.locator(PERIOD_OPTION)
    matching_options = [
        index
        for index, text in enumerate(options.all_inner_texts())
        if text.strip() == target
    ]
    if not matching_options:
        raise CollectorDataError(f"详情页下拉菜单未找到时间选项：{target}。")
    options.nth(matching_options[-1]).click()


def _notes_rate_response(response: Any) -> bool:
    return (
        response.request.method == "GET"
        and response.url.split("?", 1)[0].endswith(NOTES_RATE_API_PATH)
    )


def _click_cooperation_notes(page: Any, timeout_ms: int) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    buttons = page.locator("button")
    matches = [
        index
        for index, text in enumerate(buttons.all_inner_texts())
        if text.strip() == "合作笔记"
    ]
    if not matches:
        raise CollectorDataError("博主详情页未找到“合作笔记”入口。")
    try:
        with page.expect_response(_notes_rate_response, timeout=timeout_ms) as response_info:
            buttons.nth(matches[-1]).click()
        return response_info.value.json()
    except PlaywrightTimeoutError as error:
        raise CollectorDataError("切换合作笔记后未获取到详情指标。") from error


def _select_detail_metrics(
    page: Any,
    days: int,
    timeout_ms: int,
) -> dict[str, int]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        with page.expect_response(_notes_rate_response, timeout=timeout_ms) as response_info:
            select_detail_period(page, days)
        return parse_detail_metrics(response_info.value.json())
    except PlaywrightTimeoutError as error:
        raise CollectorDataError(f"切换近{days}日后未获取到详情指标。") from error


def find_detail_result_avatar(page: Any) -> Any:
    avatars = page.locator(DETAIL_RESULT_ROW)
    if avatars.count() == 0:
        raise CollectorDataError("搜索结果头像未加载。")
    return avatars.first


def collect_snapshot_in_context(
    context: Any,
    blogger: Blogger,
    crawl_month: str,
    config: dict[str, dict[str, str]],
    project_root: Path,
    *,
    search_url: str | None = None,
    timeout_ms: int | None = None,
) -> Snapshot:
    source_config = config.get("source", {})
    login_url = source_config.get("login_url", "https://example.com/").strip()
    resolved_search_url = search_url or source_config.get("search_url") or (
        login_url.rstrip("/") + "/dashboard/note/kol"
    )
    resolved_timeout_ms = timeout_ms or _as_int(source_config.get("request_timeout_ms"), 30_000)
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        PlaywrightTimeoutError = TimeoutError

    page = context.new_page()
    try:
        page.goto(resolved_search_url, wait_until="domcontentloaded", timeout=resolved_timeout_ms)
        if PROTECTED_PATH_PREFIX not in page.url or page.get_by_text("账号登录", exact=True).count():
            raise SessionExpired("登录态已失效，请重新运行 --login。")

        field = prepare_search_page(page, resolved_timeout_ms)
        search_payloads: list[dict[str, Any]] = []

        def capture_search_response(response: Any) -> None:
            if (
                response.request.method == "POST"
                and response.url.split("?", 1)[0].endswith(SEARCH_API_PATH)
            ):
                try:
                    search_payloads.append(response.json())
                except Exception:
                    pass

        page.on("response", capture_search_response)
        try:
            field.fill(blogger.red_id)
            field.press("Enter")
            payload = None
            for _ in range(max(1, resolved_timeout_ms // 250)):
                try:
                    payload = select_search_payload(search_payloads, blogger)
                    break
                except CollectorDataError:
                    page.wait_for_timeout(250)
            if payload is None:
                payload = select_search_payload(search_payloads, blogger)
        except PlaywrightTimeoutError as error:
            raise CollectorDataError(
                f"搜索博主超时：{blogger.nickname or blogger.red_id}。"
            ) from error
        snapshot = parse_snapshot(payload, blogger, crawl_month)
        detail_page = None
        try:
            page.wait_for_selector(
                DETAIL_RESULT_ROW,
                timeout=resolved_timeout_ms,
            )
            with page.expect_popup(timeout=resolved_timeout_ms) as popup_info:
                find_detail_result_avatar(page).click(force=True)
            detail_page = popup_info.value
            detail_page.wait_for_load_state("domcontentloaded", timeout=resolved_timeout_ms)
            detail_page.wait_for_timeout(min(3000, resolved_timeout_ms))
            metrics_30d = parse_detail_metrics(
                _click_cooperation_notes(detail_page, resolved_timeout_ms)
            )
            metrics_90d = _select_detail_metrics(detail_page, 90, resolved_timeout_ms)
        except PlaywrightTimeoutError as error:
            raise CollectorDataError(
                f"打开博主详情页超时：{blogger.nickname or blogger.red_id}。"
            ) from error
        finally:
            if detail_page is not None:
                detail_page.close()
    finally:
        page.close()

    return replace(
        snapshot,
        note_count_30d=metrics_30d["note_count"],
        exposure_median_30d=metrics_30d["exposure_median"],
        read_median_30d=metrics_30d["read_median"],
        interaction_median_30d=metrics_30d["interaction_median"],
        note_count_90d=metrics_90d["note_count"],
        exposure_median_90d=metrics_90d["exposure_median"],
        read_median_90d=metrics_90d["read_median"],
        interaction_median_90d=metrics_90d["interaction_median"],
    )


def collect_snapshot(
    blogger: Blogger,
    crawl_month: str,
    config: dict[str, dict[str, str]],
    project_root: Path,
    *,
    playwright_factory: Callable[[], object] | None = None,
) -> Snapshot:
    source_config = config.get("source", {})
    session_path = validate_session(source_config, project_root)

    if playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserAutomationUnavailable(
                "未安装 Playwright。请先运行: python -m pip install -r requirements.txt，"
                "再运行: python -m playwright install chromium。"
            ) from error
        playwright_factory = sync_playwright

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = None
        try:
            context = browser.new_context(storage_state=str(session_path))
            return collect_snapshot_in_context(
                context,
                blogger,
                crawl_month,
                config,
                project_root,
            )
        finally:
            if context is not None:
                context.close()
            browser.close()
