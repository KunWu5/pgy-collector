from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .models import Snapshot


EXPORT_COLUMNS = [
    ("crawl_month", "采集月份"),
    ("red_id", "博主ID"),
    ("nickname", "账户名"),
    ("data_source", "数据来源"),
    ("is_real_collection", "是否真实采集"),
    ("data_remark", "备注"),
    ("fans_count", "粉丝数"),
    ("image_price", "图文报价"),
    ("video_price", "视频报价"),
    ("tags", "标签"),
    ("note_count_30d", "近30天合作笔记数"),
    ("exposure_median_30d", "近30天曝光中位数"),
    ("read_median_30d", "近30天阅读中位数"),
    ("interaction_median_30d", "近30天互动中位数"),
    ("note_count_90d", "近90天合作笔记数"),
    ("exposure_median_90d", "近90天曝光中位数"),
    ("read_median_90d", "近90天阅读中位数"),
    ("interaction_median_90d", "近90天互动中位数"),
    ("crawl_status", "采集状态"),
    ("error_message", "失败原因"),
    ("crawled_at", "采集时间"),
]


def _display_value(snapshot: Snapshot, field: str, data_source: str) -> object:
    if field == "data_source":
        return "真实采集" if data_source == "real" else "离线模拟"
    if field == "is_real_collection":
        return "是" if data_source == "real" else "否"
    if field == "data_remark":
        if data_source == "real":
            return "来自详情页合作笔记的真实采集结果；近30日和近90日指标均为页面原始数据"
        return "当前指标为模拟数据，待账号接入后替换为真实采集"
    value = getattr(snapshot, field)
    if field == "tags":
        return ", ".join(value)
    if field == "crawled_at":
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def export_snapshots(
    snapshots: list[Snapshot],
    path: str | Path,
    data_source: str = "mock",
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "采集数据"
    worksheet.append([label for _, label in EXPORT_COLUMNS])

    for snapshot in snapshots:
        worksheet.append(
            [_display_value(snapshot, field, data_source) for field, _ in EXPORT_COLUMNS]
        )

    if worksheet.max_row >= 2:
        for (red_id_cell,) in worksheet.iter_rows(
            min_row=2,
            max_row=worksheet.max_row,
            min_col=2,
            max_col=2,
        ):
            red_id_cell.value = str(red_id_cell.value)
            red_id_cell.number_format = "@"
            red_id_cell.alignment = Alignment(horizontal="left", vertical="center")

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    widths = [12, 18, 18, 12, 14, 48, 12, 12, 12, 24, 18, 20, 20, 20, 18, 20, 20, 20, 12, 28, 20]
    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = width
    worksheet.freeze_panes = "A2"
    workbook.save(output_path)
    return output_path
