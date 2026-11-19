"""BI 数据包导出。

把 exports/ 下各月结果表整理成 FineBI / Power BI 可直接导入的中文表头数据表：
- bloggers.xlsx           博主维表（名单基础信息）
- blogger_snapshots.xlsx  月度快照事实表（含 CPM/CPE 等派生指标与分层）
- crawl_runs.xlsx         每月运行记录
- blogger_changes.xlsx    相邻月份环比宽表（含溢价预警标记）
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .analysis import (
    BloggerAnalysis,
    ChangeRow,
    build_analysis,
    build_change_rows,
    load_snapshots_from_result_excel,
)
from .importer import load_bloggers
from .models import Snapshot

_RESULT_PATTERN = re.compile(r"^(\d{4}-\d{2})_(real|mock)_result\.xlsx$")

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def discover_result_months(export_dir: str | Path, mode: str = "real") -> list[str]:
    """按文件名识别可用的采集月份，升序返回。"""
    months: list[str] = []
    if not Path(export_dir).exists():
        return months
    for entry in Path(export_dir).iterdir():
        match = _RESULT_PATTERN.match(entry.name)
        if match and match.group(2) == mode:
            months.append(match.group(1))
    return sorted(set(months))


def _new_sheet(title: str, headers: list[str]):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = title
    worksheet.append(headers)
    for cell in worksheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
    return workbook, worksheet


def _num(value: Decimal | None):
    return float(value) if value is not None else None


def _snapshot_row(row: BloggerAnalysis) -> list:
    return [
        row.red_id,
        row.nickname,
        row.fans_count,
        row.fans_tier,
        float(row.image_price),
        float(row.video_price),
        row.note_count_30d,
        row.exposure_median_30d,
        row.read_median_30d,
        row.interaction_median_30d,
        ", ".join(row.tags),
        _num(row.cpm_image),
        _num(row.cpm_video),
        _num(row.cpe_video),
        _num(row.cost_per_read),
        _num(row.interaction_rate),
        row.value_tier or "不可排名",
        "; ".join(row.quality_flags) if row.quality_flags else "",
    ]


def _change_row(row: ChangeRow) -> list:
    return [
        row.red_id,
        row.nickname,
        row.fans_current,
        row.fans_previous,
        _num(row.fans_change_pct),
        float(row.video_price_current),
        float(row.video_price_previous),
        _num(row.video_price_change_pct),
        row.exposure_current,
        row.exposure_previous,
        _num(row.exposure_change_pct),
        row.interaction_current,
        row.interaction_previous,
        _num(row.interaction_change_pct),
        _num(row.divergence_pp),
        row.alert,
    ]


def export_bi_package(
    export_dir: str | Path,
    blogger_list_path: str | Path,
    out_dir: str | Path,
    mode: str = "real",
    threshold_percent: float = 30.0,
) -> dict[str, Path]:
    """导出 BI 数据包，返回各数据表路径。"""
    export_path = Path(export_dir)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    months = discover_result_months(export_path, mode)
    if not months:
        raise FileNotFoundError(f"No result files found in {export_path} for mode {mode}.")

    snapshots_by_month: dict[str, list[Snapshot]] = {}
    analyses_by_month: dict[str, list[BloggerAnalysis]] = {}
    for month in months:
        result_file = export_path / f"{month}_{mode}_result.xlsx"
        snapshots = load_snapshots_from_result_excel(result_file)
        snapshots_by_month[month] = snapshots
        analyses_by_month[month] = build_analysis(snapshots)

    # 1) 博主维表
    bloggers = load_bloggers(blogger_list_path)
    workbook, sheet = _new_sheet(
        "博主名单",
        ["博主ID", "账户名", "分组", "备注", "状态"],
    )
    for blogger in bloggers:
        sheet.append([blogger.red_id, blogger.nickname or "", blogger.group_name or "", blogger.remark or "", "active"])
    blogger_table = out_path / "bloggers.xlsx"
    workbook.save(blogger_table)

    # 2) 月度快照事实表（含派生指标）
    workbook, sheet = _new_sheet(
        "月度快照",
        [
            "采集月份", "博主ID", "账户名", "粉丝数", "粉丝分层",
            "图文报价", "视频报价", "近30天笔记数", "近30天曝光中位数",
            "近30天阅读中位数", "近30天互动中位数", "标签",
            "CPM图文", "CPM视频", "CPE视频", "单阅读成本", "互动率(%)",
            "性价比分层", "质量标记",
        ],
    )
    for month in months:
        for row in analyses_by_month[month]:
            sheet.append([month] + _snapshot_row(row))
    snapshot_table = out_path / "blogger_snapshots.xlsx"
    workbook.save(snapshot_table)

    # 3) 运行记录
    workbook, sheet = _new_sheet(
        "运行记录",
        ["采集月份", "博主总数", "成功数", "失败数", "运行状态", "最后采集时间"],
    )
    for month in months:
        snapshots = snapshots_by_month[month]
        success = sum(1 for snapshot in snapshots if snapshot.crawl_status == "success")
        failed = len(snapshots) - success
        last_time = max(
            (snapshot.crawled_at for snapshot in snapshots), default=None
        )
        sheet.append(
            [
                month,
                len(snapshots),
                success,
                failed,
                "success" if failed == 0 else "partial",
                last_time.strftime("%Y-%m-%d %H:%M:%S") if last_time else "",
            ]
        )
    runs_table = out_path / "crawl_runs.xlsx"
    workbook.save(runs_table)

    # 4) 相邻月份环比宽表
    workbook, sheet = _new_sheet(
        "环比变化",
        [
            "上期月份", "本期月份", "博主ID", "账户名",
            "粉丝数_本期", "粉丝数_上期", "粉丝变化(%)",
            "视频报价_本期", "视频报价_上期", "报价变化(%)",
            "曝光_本期", "曝光_上期", "曝光变化(%)",
            "互动_本期", "互动_上期", "互动变化(%)",
            "报价互动涨幅差(pp)", "预警",
        ],
    )
    for previous_month, current_month in zip(months, months[1:]):
        rows = build_change_rows(
            snapshots_by_month[current_month],
            snapshots_by_month[previous_month],
            threshold_percent,
        )
        for row in rows:
            sheet.append([previous_month, current_month] + _change_row(row))
    changes_table = out_path / "blogger_changes.xlsx"
    workbook.save(changes_table)

    return {
        "bloggers": blogger_table,
        "blogger_snapshots": snapshot_table,
        "crawl_runs": runs_table,
        "blogger_changes": changes_table,
    }
