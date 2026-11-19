from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Snapshot


REPORT_METRICS = [
    ("fans_count", "粉丝数"),
    ("image_price", "图文报价"),
    ("video_price", "视频报价"),
    ("note_count_30d", "近30天合作笔记数"),
    ("exposure_median_30d", "近30天曝光中位数"),
    ("read_median_30d", "近30天阅读中位数"),
    ("interaction_median_30d", "近30天互动中位数"),
    ("note_count_90d", "近90天合作笔记数"),
    ("exposure_median_90d", "近90天曝光中位数"),
    ("read_median_90d", "近90天阅读中位数"),
    ("interaction_median_90d", "近90天互动中位数"),
]

REPORT_COLUMNS = [
    ("red_id", "博主ID"),
    ("nickname", "账户名"),
    ("metric_label", "指标"),
    ("current_value", "本月值"),
    ("previous_value", "上月值"),
    ("delta", "变化值"),
    ("change_percent", "变化比例"),
    ("status", "状态"),
]


def _numeric(value: object) -> int | float | Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return value
    return Decimal(str(value))


def _excel_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


def build_change_rows(
    current_snapshots: Iterable[Snapshot],
    previous_snapshots: Iterable[Snapshot],
    threshold_percent: float = 30.0,
) -> list[dict[str, object]]:
    if threshold_percent < 0:
        raise ValueError("threshold_percent cannot be negative.")
    previous_by_id = {
        snapshot.red_id: snapshot
        for snapshot in previous_snapshots
        if snapshot.crawl_status == "success"
    }
    rows: list[dict[str, object]] = []
    for current in current_snapshots:
        if current.crawl_status != "success":
            continue
        previous = previous_by_id.get(current.red_id)
        for metric_key, metric_label in REPORT_METRICS:
            current_value = _numeric(getattr(current, metric_key))
            previous_value = _numeric(getattr(previous, metric_key)) if previous else None
            delta = None
            change_percent = None
            is_alert = False
            if previous is None:
                status = "无上月数据"
            elif current_value is None:
                status = "本月无数据"
            elif previous_value is None:
                status = "上月无数据"
            elif previous_value == 0:
                delta = current_value - previous_value
                status = "上月为0"
            else:
                delta = current_value - previous_value
                change_percent = round(float(delta / abs(previous_value) * 100), 2)
                is_alert = abs(change_percent) >= threshold_percent
                status = "异常波动" if is_alert else "正常"
            rows.append(
                {
                    "red_id": current.red_id,
                    "nickname": current.nickname,
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "current_value": current_value,
                    "previous_value": previous_value,
                    "delta": delta,
                    "change_percent": change_percent,
                    "status": status,
                    "is_alert": is_alert,
                }
            )
    return rows


def _write_sheet(workbook: Workbook, title: str, rows: list[dict[str, object]]) -> None:
    worksheet = workbook.create_sheet(title)
    worksheet.append([label for _, label in REPORT_COLUMNS])
    for row in rows:
        worksheet.append([_excel_value(row.get(key)) for key, _ in REPORT_COLUMNS])

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = [18, 18, 24, 16, 16, 16, 16, 14]
    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = width
    worksheet.freeze_panes = "A2"
    for row in worksheet.iter_rows(min_row=2, min_col=7, max_col=7):
        row[0].number_format = "0.00"


def export_monthly_report(
    rows: list[dict[str, object]],
    alerts: list[dict[str, object]],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)
    _write_sheet(workbook, "月度变化", rows)
    _write_sheet(workbook, "异常提醒", alerts)
    workbook.save(output_path)
    return output_path
