"""博主性价比分析层。

基于采集快照计算投放派生指标（CPM/CPE/单阅读成本/互动率），
做粉丝分层与性价比分层，输出可直接用于投放筛选的榜单与环比预警。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Snapshot

# ---- 分层口径 ----

FANS_TIERS = (
    (500_000, "头部(≥50万)"),
    (100_000, "腰部(10-50万)"),
    (10_000, "初级(1-10万)"),
    (0, "KOC(<1万)"),
)

VALUE_TIERS = ("高性价比", "中等偏优", "中等", "偏高")

FANS_CHANGE_ALERT_PERCENT = 50


def classify_fans_tier(fans_count: int) -> str:
    for threshold, label in FANS_TIERS:
        if fans_count >= threshold:
            return label
    return FANS_TIERS[-1][1]


@dataclass(frozen=True)
class BloggerAnalysis:
    red_id: str
    nickname: str
    fans_count: int
    fans_tier: str
    image_price: Decimal
    video_price: Decimal
    note_count_30d: int
    exposure_median_30d: int
    read_median_30d: int
    interaction_median_30d: int
    tags: list[str]
    cpm_image: Decimal | None
    cpm_video: Decimal | None
    cpe_video: Decimal | None
    cost_per_read: Decimal | None
    interaction_rate: Decimal | None
    quality_flags: tuple[str, ...]
    value_tier: str = ""

    @property
    def rankable(self) -> bool:
        """能否参与性价比排名（视频报价与近30天曝光都有效）。"""
        return self.cpm_video is not None


def _ratio(numerator: Decimal, denominator: int | Decimal) -> Decimal | None:
    if not denominator:
        return None
    value = Decimal(numerator) / Decimal(denominator)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def analyze_snapshot(snapshot: Snapshot) -> BloggerAnalysis:
    """计算单个博主的派生指标与数据质量标记。"""
    flags: list[str] = []
    if snapshot.crawl_status != "success":
        flags.append("采集失败")

    video_price = snapshot.video_price or Decimal("0")
    image_price = snapshot.image_price or Decimal("0")
    exposure = snapshot.exposure_median_30d or 0
    read = snapshot.read_median_30d or 0
    interaction = snapshot.interaction_median_30d or 0

    if not video_price:
        flags.append("视频报价缺失或为0")
    if not exposure:
        flags.append("近30天无合作笔记曝光")
    elif not read:
        flags.append("近30天阅读中位数为0")

    cpm_image = (
        _ratio(image_price * Decimal(1000), exposure) if image_price and exposure else None
    )
    cpm_video = (
        _ratio(video_price * Decimal(1000), exposure) if video_price and exposure else None
    )
    cpe_video = _ratio(video_price, interaction) if video_price and interaction else None
    cost_per_read = _ratio(video_price, read) if video_price and read else None
    interaction_rate = (
        _ratio(Decimal(interaction) * Decimal(100), read) if read else None
    )

    return BloggerAnalysis(
        red_id=snapshot.red_id,
        nickname=snapshot.nickname,
        fans_count=snapshot.fans_count,
        fans_tier=classify_fans_tier(snapshot.fans_count),
        image_price=image_price,
        video_price=video_price,
        note_count_30d=snapshot.note_count_30d or 0,
        exposure_median_30d=exposure,
        read_median_30d=read,
        interaction_median_30d=interaction,
        tags=list(snapshot.tags),
        cpm_image=cpm_image,
        cpm_video=cpm_video,
        cpe_video=cpe_video,
        cost_per_read=cost_per_read,
        interaction_rate=interaction_rate,
        quality_flags=tuple(flags),
    )


def _percentile(sorted_values: list[Decimal], fraction: float) -> Decimal:
    index = min(len(sorted_values) - 1, int(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def assign_value_tiers(rows: list[BloggerAnalysis]) -> list[BloggerAnalysis]:
    """按 CPM 四分位给可排名的博主打性价比分层，越低越划算。"""
    rankable = sorted((row for row in rows if row.rankable), key=lambda row: row.cpm_video)
    tier_by_id: dict[str, str] = {}
    if rankable:
        values = [row.cpm_video for row in rankable]
        p25 = _percentile(values, 0.25)
        p50 = _percentile(values, 0.50)
        p75 = _percentile(values, 0.75)
        for row in rankable:
            if row.cpm_video <= p25:
                tier_by_id[row.red_id] = "高性价比"
            elif row.cpm_video <= p50:
                tier_by_id[row.red_id] = "中等偏优"
            elif row.cpm_video <= p75:
                tier_by_id[row.red_id] = "中等"
            else:
                tier_by_id[row.red_id] = "偏高"
    return [replace(row, value_tier=tier_by_id.get(row.red_id, "")) for row in rows]


def build_analysis(snapshots: list[Snapshot]) -> list[BloggerAnalysis]:
    rows = [analyze_snapshot(snapshot) for snapshot in snapshots]
    return assign_value_tiers(rows)


# ---- 环比变化与溢价预警 ----


@dataclass(frozen=True)
class ChangeRow:
    red_id: str
    nickname: str
    fans_current: int
    fans_previous: int
    fans_change_pct: Decimal | None
    video_price_current: Decimal
    video_price_previous: Decimal
    video_price_change_pct: Decimal | None
    exposure_current: int
    exposure_previous: int
    exposure_change_pct: Decimal | None
    interaction_current: int
    interaction_previous: int
    interaction_change_pct: Decimal | None
    divergence_pp: Decimal | None
    alert: str


def _change_pct(current: int | Decimal, previous: int | Decimal) -> Decimal | None:
    if not previous:
        return None
    value = (Decimal(current) - Decimal(previous)) / Decimal(previous) * Decimal(100)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_change_rows(
    current: list[Snapshot],
    previous: list[Snapshot],
    threshold_percent: float = 30.0,
) -> list[ChangeRow]:
    """对比两个月快照：报价涨幅显著快于互动涨幅时标记溢价预警。"""
    previous_by_id = {snapshot.red_id: snapshot for snapshot in previous}
    rows: list[ChangeRow] = []
    for snapshot in current:
        prior = previous_by_id.get(snapshot.red_id)
        if prior is None:
            continue
        fans_pct = _change_pct(snapshot.fans_count, prior.fans_count)
        price_pct = _change_pct(snapshot.video_price, prior.video_price)
        exposure_pct = _change_pct(
            snapshot.exposure_median_30d or 0, prior.exposure_median_30d or 0
        )
        interaction_pct = _change_pct(
            snapshot.interaction_median_30d or 0, prior.interaction_median_30d or 0
        )
        divergence = (
            (price_pct - interaction_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if price_pct is not None and interaction_pct is not None
            else None
        )
        threshold = Decimal(str(threshold_percent))
        alert = ""
        if divergence is not None:
            if divergence >= threshold:
                alert = "溢价预警"
            elif divergence <= -threshold:
                alert = "性价比提升"
        if fans_pct is not None and abs(fans_pct) >= FANS_CHANGE_ALERT_PERCENT:
            alert = (alert + "+" if alert else "") + "粉丝异动"
        rows.append(
            ChangeRow(
                red_id=snapshot.red_id,
                nickname=snapshot.nickname,
                fans_current=snapshot.fans_count,
                fans_previous=prior.fans_count,
                fans_change_pct=fans_pct,
                video_price_current=snapshot.video_price,
                video_price_previous=prior.video_price,
                video_price_change_pct=price_pct,
                exposure_current=snapshot.exposure_median_30d or 0,
                exposure_previous=prior.exposure_median_30d or 0,
                exposure_change_pct=exposure_pct,
                interaction_current=snapshot.interaction_median_30d or 0,
                interaction_previous=prior.interaction_median_30d or 0,
                interaction_change_pct=interaction_pct,
                divergence_pp=divergence,
                alert=alert,
            )
        )
    return rows


# ---- 结果 Excel 加载 ----


_RESULT_FIELDS = {
    "采集月份": "crawl_month",
    "博主ID": "red_id",
    "账户名": "nickname",
    "粉丝数": "fans_count",
    "图文报价": "image_price",
    "视频报价": "video_price",
    "标签": "tags",
    "近30天合作笔记数": "note_count_30d",
    "近30天曝光中位数": "exposure_median_30d",
    "近30天阅读中位数": "read_median_30d",
    "近30天互动中位数": "interaction_median_30d",
    "近90天合作笔记数": "note_count_90d",
    "近90天曝光中位数": "exposure_median_90d",
    "近90天阅读中位数": "read_median_90d",
    "近90天互动中位数": "interaction_median_90d",
    "采集状态": "crawl_status",
    "失败原因": "error_message",
    "采集时间": "crawled_at",
}


def _to_int(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return 0


def _to_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return _to_int(value)


def _to_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.now()


def load_snapshots_from_result_excel(path: str | Path) -> list[Snapshot]:
    """从 exports/ 下的结果表加载快照，分析层因此可以在 dry-run 后直接使用。"""
    from openpyxl import load_workbook

    result_path = Path(path)
    if not result_path.exists():
        raise FileNotFoundError(f"Result file not found: {result_path}")

    workbook = load_workbook(result_path, read_only=True)
    worksheet = workbook["采集数据"]
    rows = list(worksheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        return []

    header = [str(cell) if cell is not None else "" for cell in rows[0]]
    index_by_field = {
        _RESULT_FIELDS[label]: position for position, label in enumerate(header) if label in _RESULT_FIELDS
    }

    snapshots: list[Snapshot] = []
    for values in rows[1:]:
        if not any(values):
            continue

        def cell(field: str) -> object:
            position = index_by_field.get(field)
            return values[position] if position is not None and position < len(values) else None

        tags_text = str(cell("tags") or "")
        snapshots.append(
            Snapshot(
                red_id=str(cell("red_id") or "").strip(),
                crawl_month=str(cell("crawl_month") or "").strip(),
                nickname=str(cell("nickname") or "").strip(),
                fans_count=_to_int(cell("fans_count")),
                image_price=_to_decimal(cell("image_price")),
                video_price=_to_decimal(cell("video_price")),
                tags=[tag.strip() for tag in tags_text.split(",") if tag.strip()],
                note_count_30d=_to_int(cell("note_count_30d")),
                exposure_median_30d=_to_int(cell("exposure_median_30d")),
                read_median_30d=_to_int(cell("read_median_30d")),
                interaction_median_30d=_to_int(cell("interaction_median_30d")),
                note_count_90d=_to_optional_int(cell("note_count_90d")),
                exposure_median_90d=_to_optional_int(cell("exposure_median_90d")),
                read_median_90d=_to_optional_int(cell("read_median_90d")),
                interaction_median_90d=_to_optional_int(cell("interaction_median_90d")),
                crawl_status=str(cell("crawl_status") or "").strip() or "unknown",
                error_message=(str(cell("error_message")) if cell("error_message") else None),
                crawled_at=_to_datetime(cell("crawled_at")),
            )
        )
    return snapshots


# ---- 分析报告导出 ----


_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_ALERT_FILL = PatternFill("solid", fgColor="FCE4E4")
_GOOD_FILL = PatternFill("solid", fgColor="E2F0D9")


def _style_header(worksheet) -> None:
    for cell in worksheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.freeze_panes = "A2"


def _set_widths(worksheet, widths: list[int]) -> None:
    for position, width in enumerate(widths, start=1):
        worksheet.column_dimensions[get_column_letter(position)].width = width


def export_analysis_report(
    analyses: list[BloggerAnalysis],
    changes: list[ChangeRow],
    path: str | Path,
    crawl_month: str,
    previous_month: str | None = None,
) -> Path:
    """导出分析报告 Excel：摘要 / 分析总览 / 性价比榜单 / 环比与溢价预警。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rankable = sorted(
        (row for row in analyses if row.rankable), key=lambda row: row.cpm_video
    )
    workbook = Workbook()

    # Sheet 1: 摘要
    summary = workbook.active
    summary.title = "摘要"
    summary.append(["指标", "数值"])
    tier_counts = {label: 0 for _, label in FANS_TIERS}
    value_counts = {label: 0 for label in VALUE_TIERS}
    for row in analyses:
        tier_counts[row.fans_tier] = tier_counts.get(row.fans_tier, 0) + 1
        if row.value_tier:
            value_counts[row.value_tier] = value_counts.get(row.value_tier, 0) + 1
    cpm_values = [row.cpm_video for row in rankable]
    median_cpm = None
    if cpm_values:
        mid = len(cpm_values) // 2
        if len(cpm_values) % 2:
            median_cpm = cpm_values[mid]
        else:
            median_cpm = (cpm_values[mid - 1] + cpm_values[mid]) / 2
    summary.append(["统计月份", crawl_month])
    summary.append(["博主总数", len(analyses)])
    summary.append(["可参与性价比排名", len(rankable)])
    summary.append(["CPM中位数(元/千次曝光)", median_cpm if median_cpm is not None else "无有效数据"])
    for _, label in FANS_TIERS:
        summary.append([f"粉丝分层-{label}", tier_counts.get(label, 0)])
    for label in VALUE_TIERS:
        summary.append([f"性价比分层-{label}", value_counts.get(label, 0)])
    summary.append(["环比月份", previous_month or "无"])
    summary.append(["环比博主数", len(changes)])
    summary.append(["溢价预警数", sum(1 for row in changes if "溢价预警" in row.alert)])
    summary.append(["性价比提升数", sum(1 for row in changes if "性价比提升" in row.alert)])
    summary.append(["粉丝异动数", sum(1 for row in changes if "粉丝异动" in row.alert)])
    summary.append(["", ""])
    summary.append(["指标口径", "说明"])
    summary.append(["CPM", "视频报价 / 近30天曝光中位数 × 1000（元/千次曝光），越低投放性价比越高"])
    summary.append(["CPE", "视频报价 / 近30天互动中位数（元/次互动）"])
    summary.append(["单阅读成本", "视频报价 / 近30天阅读中位数（元/次阅读）"])
    summary.append(["互动率", "近30天互动中位数 / 近30天阅读中位数 × 100（%）"])
    summary.append(["性价比分层", "按 CPM 四分位划分：高性价比 = CPM 处于最低 25%"])
    summary.append(["溢价预警", "视频报价涨幅 − 互动涨幅 ≥ 30 个百分点"])
    _style_header(summary)
    _set_widths(summary, [22, 60])

    # Sheet 2: 分析总览
    overview = workbook.create_sheet("分析总览")
    overview.append(
        [
            "博主ID", "账户名", "粉丝数", "粉丝分层", "图文报价", "视频报价",
            "CPM(图文)", "CPM(视频)", "CPE(视频)", "单阅读成本", "互动率(%)",
            "近30天笔记数", "近30天曝光", "近30天阅读", "近30天互动",
            "性价比分层", "质量标记", "标签",
        ]
    )
    for row in analyses:
        overview.append(
            [
                row.red_id, row.nickname, row.fans_count, row.fans_tier,
                float(row.image_price), float(row.video_price),
                float(row.cpm_image) if row.cpm_image is not None else None,
                float(row.cpm_video) if row.cpm_video is not None else None,
                float(row.cpe_video) if row.cpe_video is not None else None,
                float(row.cost_per_read) if row.cost_per_read is not None else None,
                float(row.interaction_rate) if row.interaction_rate is not None else None,
                row.note_count_30d, row.exposure_median_30d, row.read_median_30d,
                row.interaction_median_30d, row.value_tier or "不可排名",
                "; ".join(row.quality_flags) if row.quality_flags else "",
                ", ".join(row.tags),
            ]
        )
    _style_header(overview)
    _set_widths(overview, [16, 18, 10, 14, 10, 10, 10, 10, 10, 12, 10, 12, 12, 12, 12, 12, 30, 40])

    # Sheet 3: 性价比榜单
    ranking = workbook.create_sheet("性价比榜单")
    ranking.append(
        [
            "排名", "博主ID", "账户名", "粉丝数", "粉丝分层", "视频报价",
            "CPM(视频)", "CPE(视频)", "单阅读成本", "互动率(%)",
            "近30天笔记数", "近30天曝光", "近30天互动", "标签",
        ]
    )
    for position, row in enumerate(rankable, start=1):
        ranking.append(
            [
                position, row.red_id, row.nickname, row.fans_count, row.fans_tier,
                float(row.video_price), float(row.cpm_video),
                float(row.cpe_video) if row.cpe_video is not None else None,
                float(row.cost_per_read) if row.cost_per_read is not None else None,
                float(row.interaction_rate) if row.interaction_rate is not None else None,
                row.note_count_30d, row.exposure_median_30d, row.interaction_median_30d,
                ", ".join(row.tags),
            ]
        )
    _style_header(ranking)
    _set_widths(ranking, [8, 16, 18, 10, 14, 10, 10, 10, 12, 10, 12, 12, 12, 40])
    if ranking.max_row >= 2:
        for row_index in range(2, ranking.max_row + 1):
            if row_index - 1 <= len(rankable) * 0.25:
                for cell in ranking[row_index]:
                    cell.fill = _GOOD_FILL

    # Sheet 4: 环比与溢价预警
    if changes:
        change_sheet = workbook.create_sheet("环比与溢价预警")
        change_sheet.append(
            [
                "博主ID", "账户名", "预警", "粉丝数(本期)", "粉丝数(上期)", "粉丝变化(%)",
                "视频报价(本期)", "视频报价(上期)", "报价变化(%)",
                "30天曝光(本期)", "30天曝光(上期)", "曝光变化(%)",
                "30天互动(本期)", "30天互动(上期)", "互动变化(%)",
                "报价-互动涨幅差(百分点)",
            ]
        )
        ordered = sorted(
            changes,
            key=lambda row: (0 if "溢价预警" in row.alert else 1 if row.alert else 2, row.red_id),
        )
        for row in ordered:
            change_sheet.append(
                [
                    row.red_id, row.nickname, row.alert or "",
                    row.fans_current, row.fans_previous,
                    float(row.fans_change_pct) if row.fans_change_pct is not None else None,
                    float(row.video_price_current), float(row.video_price_previous),
                    float(row.video_price_change_pct) if row.video_price_change_pct is not None else None,
                    row.exposure_current, row.exposure_previous,
                    float(row.exposure_change_pct) if row.exposure_change_pct is not None else None,
                    row.interaction_current, row.interaction_previous,
                    float(row.interaction_change_pct) if row.interaction_change_pct is not None else None,
                    float(row.divergence_pp) if row.divergence_pp is not None else None,
                ]
            )
        _style_header(change_sheet)
        _set_widths(change_sheet, [16, 18, 16, 14, 14, 12, 14, 14, 12, 14, 14, 12, 14, 14, 12, 20])
        if change_sheet.max_row >= 2:
            for row_index in range(2, change_sheet.max_row + 1):
                if "溢价预警" in str(change_sheet.cell(row_index, 3).value):
                    for cell in change_sheet[row_index]:
                        cell.fill = _ALERT_FILL
                elif "性价比提升" in str(change_sheet.cell(row_index, 3).value):
                    for cell in change_sheet[row_index]:
                        cell.fill = _GOOD_FILL

    workbook.save(output_path)
    return output_path
