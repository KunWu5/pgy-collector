from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .analysis import (
    build_analysis as build_value_analysis,
    build_change_rows as build_value_change_rows,
    export_analysis_report,
    load_snapshots_from_result_excel,
)
from .browser_auth import (
    BrowserAutomationUnavailable,
    LoginUrlNotConfigured,
    LoginTimeout,
    run_manual_browser_login,
)
from .backup import backup_mysql
from .checkpoint import CheckpointError
from .collectors import build_collector
from .config import ConfigError, load_simple_yaml, resolve_config_secrets
from .db import MySQLRepository, require_mysql_connector
from .db_cli import MySQLCliRepository
from .export_bi import export_bi_package
from .exporter import export_snapshots
from .importer import load_bloggers
from .web_collector import CollectorNotConfigured
from .report import build_change_rows, export_monthly_report
from .runner import collect_snapshots


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def export_filename(crawl_month: str, mode: str) -> str:
    suffix = "real" if mode.strip().lower() == "real" else "mock"
    return f"{crawl_month}_{suffix}_result.xlsx"


def log_filename(crawl_month: str, mode: str) -> str:
    suffix = "real" if mode.strip().lower() == "real" else "mock"
    return f"{crawl_month}_{suffix}_run.log"


def previous_month(crawl_month: str) -> str:
    if len(crawl_month) != 7 or crawl_month[4] != "-":
        raise ValueError(f"Invalid crawl month: {crawl_month}")
    first_day = date.fromisoformat(f"{crawl_month}-01")
    return (first_day - timedelta(days=1)).strftime("%Y-%m")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pugongying blogger crawler MVP")
    parser.add_argument("--config", default="config.yaml", help="Path to local config YAML")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip MySQL and export the result selected by run.mode",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--login", action="store_true", help="Prepare Pugongying login session")
    actions.add_argument("--backup", action="store_true", help="Backup the configured MySQL database")
    actions.add_argument("--reset-month", help="Remove snapshots and runs for a month before the formal crawl")
    actions.add_argument("--report", action="store_true", help="Generate a month-over-month report")
    actions.add_argument(
        "--analyze",
        action="store_true",
        help="Generate the blogger value analysis report (CPM/CPE tiers) from the exported result Excel",
    )
    actions.add_argument(
        "--export-bi",
        action="store_true",
        help="Export BI-ready data tables (bloggers/snapshots/runs/changes) to the bi/ directory",
    )
    parser.add_argument("--yes", action="store_true", help="Confirm a destructive reset action")
    parser.add_argument("--month", default=None, help="Override crawl month, for example 2026-07")
    parser.add_argument(
        "--prev-month",
        default=None,
        help="Previous month for the value analysis comparison, default is the month before --month",
    )
    resume_actions = parser.add_mutually_exclusive_group()
    resume_actions.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the local checkpoint and retry unfinished bloggers",
    )
    resume_actions.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry only failed bloggers from the local checkpoint",
    )
    return parser


def load_config(
    config_path: str,
    resolve_secrets: bool = True,
) -> tuple[Path, dict[str, dict[str, str]]]:
    project_root = Path(__file__).resolve().parents[2]
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = project_root / config_file
    config = load_simple_yaml(config_file)
    if resolve_secrets:
        config = resolve_config_secrets(config)
    return project_root, config


def run_login(config_path: str) -> int:
    project_root, config = load_config(config_path, resolve_secrets=False)
    session_path = run_manual_browser_login(config, project_root)
    print(f"登录态已保存：{session_path}")
    return 0


def run_backup(config_path: str) -> int:
    project_root, config = load_config(config_path)
    backup_dir = project_root / config.get("output", {}).get("backup_dir", "backups")
    output_path = backup_mysql(config["mysql"], project_root, backup_dir)
    print(f"MySQL备份已生成：{output_path}")
    return 0


def run_reset_month(config_path: str, crawl_month: str, confirmed: bool) -> int:
    if not confirmed:
        print("清理月份数据属于破坏性操作，请同时提供 --yes。", file=sys.stderr)
        return 2
    project_root, config = load_config(config_path)
    try:
        require_mysql_connector()
        repository = MySQLRepository(config["mysql"])
        try:
            repository.clear_month(crawl_month)
        finally:
            repository.close()
    except RuntimeError as error:
        if "Missing MySQL driver" not in str(error):
            raise
        repository = MySQLCliRepository(config["mysql"], project_root)
        repository.clear_month(crawl_month)
    print(f"已清理 {crawl_month} 的快照和运行记录，未删除博主基础名单。")
    return 0


def run_report(config_path: str, month: str | None) -> int:
    project_root, config = load_config(config_path)
    crawl_month = month or config.get("run", {}).get("crawl_month") or current_month()
    if crawl_month == "auto":
        crawl_month = current_month()
    previous = previous_month(crawl_month)
    threshold = float(config.get("report", {}).get("alert_threshold_percent", "30"))
    report_dir = project_root / config.get("output", {}).get("report_dir", "reports")
    report_path = report_dir / f"{crawl_month}_change_report.xlsx"

    require_mysql_connector()
    repository = MySQLRepository(config["mysql"])
    try:
        current_snapshots = repository.get_snapshots_for_month(crawl_month)
        previous_snapshots = repository.get_snapshots_for_month(previous)
    finally:
        repository.close()

    rows = build_change_rows(current_snapshots, previous_snapshots, threshold)
    alerts = [row for row in rows if row["is_alert"]]
    export_monthly_report(rows, alerts, report_path)
    print(f"月度报告已生成：{report_path}")
    print(f"比较月份：{previous} -> {crawl_month}；异常提醒 {len(alerts)} 条")
    return 0


def run_analyze(config_path: str, month: str | None, prev_month: str | None) -> int:
    """基于 exports/ 结果表生成性价比分析报告，不依赖 MySQL。"""
    project_root, config = load_config(config_path, resolve_secrets=False)
    crawl_month = month or config.get("run", {}).get("crawl_month") or current_month()
    if crawl_month == "auto":
        crawl_month = current_month()
    mode = config.get("run", {}).get("mode", "mock").strip().lower()
    export_dir = project_root / config.get("output", {}).get("export_dir", "exports")
    current_path = export_dir / export_filename(crawl_month, mode)
    if not current_path.exists():
        print(f"未找到本期结果表：{current_path}，请先完成该月采集。", file=sys.stderr)
        return 2

    current_snapshots = load_snapshots_from_result_excel(current_path)

    comparison_month = prev_month or previous_month(crawl_month)
    previous_path = export_dir / export_filename(comparison_month, mode)
    previous_snapshots: list = []
    if previous_path.exists():
        previous_snapshots = load_snapshots_from_result_excel(previous_path)
    else:
        comparison_month = ""

    threshold = float(config.get("report", {}).get("alert_threshold_percent", "30"))
    analyses = build_value_analysis(current_snapshots)
    changes = build_value_change_rows(current_snapshots, previous_snapshots, threshold)

    report_dir = project_root / config.get("output", {}).get("report_dir", "reports")
    report_path = report_dir / f"{crawl_month}_analysis.xlsx"
    export_analysis_report(
        analyses,
        changes,
        report_path,
        crawl_month,
        comparison_month or None,
    )

    rankable = [row for row in analyses if row.rankable]
    ranked = sorted(rankable, key=lambda row: row.cpm_video)
    alert_count = sum(1 for row in changes if "溢价预警" in row.alert)
    print(f"性价比分析报告已生成：{report_path}")
    print(f"博主 {len(analyses)} 位，其中 {len(rankable)} 位可参与 CPM 排名")
    if ranked:
        mid = len(ranked) // 2
        if len(ranked) % 2:
            median = ranked[mid].cpm_video
        else:
            median = (ranked[mid - 1].cpm_video + ranked[mid].cpm_video) / 2
        print(f"CPM 中位数：{median} 元/千次曝光")
        print("CPM 最优前 5 位：")
        for position, row in enumerate(ranked[:5], start=1):
            print(f"  {position}. {row.nickname}（{row.fans_tier}）CPM {row.cpm_video}")
    if comparison_month:
        print(f"环比 {comparison_month} -> {crawl_month}：{len(changes)} 位可比，溢价预警 {alert_count} 条")
    else:
        print("未找到上期结果表，跳过环比分析")
    return 0


def run_export_bi(config_path: str) -> int:
    """把各月结果表导出为 BI 可直接导入的数据包。"""
    project_root, config = load_config(config_path, resolve_secrets=False)
    mode = config.get("run", {}).get("mode", "mock").strip().lower()
    export_dir = project_root / config.get("output", {}).get("export_dir", "exports")
    blogger_list = project_root / config["input"]["blogger_list"]
    bi_dir = project_root / config.get("output", {}).get("bi_dir", "bi")
    threshold = float(config.get("report", {}).get("alert_threshold_percent", "30"))
    tables = export_bi_package(export_dir, blogger_list, bi_dir, mode, threshold)
    print(f"BI 数据包已导出到：{bi_dir}")
    for name, path in tables.items():
        print(f"  {name}: {path.name}")
    return 0


def run(
    config_path: str,
    dry_run: bool,
    month: str | None,
    *,
    resume: bool = False,
    retry_failed: bool = False,
) -> int:
    project_root, config = load_config(config_path, resolve_secrets=not dry_run)

    crawl_month = month or config.get("run", {}).get("crawl_month") or current_month()
    if crawl_month == "auto":
        crawl_month = current_month()

    mode = config.get("run", {}).get("mode", "mock").strip().lower()
    input_path = project_root / config["input"]["blogger_list"]
    export_dir = project_root / config.get("output", {}).get("export_dir", "exports")
    export_path = export_dir / export_filename(crawl_month, mode)
    log_dir = project_root / config.get("output", {}).get("log_dir", "logs")
    log_path = log_dir / log_filename(crawl_month, mode)
    checkpoint_dir = project_root / config.get("run", {}).get(
        "checkpoint_dir", "runtime/checkpoints"
    )
    checkpoint_path = checkpoint_dir / f"{crawl_month}_{mode}.json"
    retry_count = int(config.get("run", {}).get("retry_count", "2"))

    bloggers = load_bloggers(input_path)
    collector = build_collector(config, project_root)
    snapshots = collect_snapshots(
        bloggers,
        crawl_month,
        collector,
        log_path,
        retry_count=retry_count,
        checkpoint_path=checkpoint_path,
        resume=resume,
        retry_failed=retry_failed,
    )
    exported = export_snapshots(snapshots, export_path, data_source=mode)
    success_count = sum(1 for snapshot in snapshots if snapshot.crawl_status == "success")
    failed_count = len(snapshots) - success_count

    print(f"读取 {len(bloggers)} 个博主")
    print(f"已导出 {exported}")
    print(f"运行日志 {log_path}")

    if dry_run:
        print("dry-run 模式：已跳过 MySQL 写入")
        return 0

    try:
        require_mysql_connector()
        repository = MySQLRepository(config["mysql"])
        try:
            blogger_ids = repository.sync_bloggers(bloggers)
            run_id = repository.create_run(crawl_month, len(bloggers))
            repository.upsert_snapshots(snapshots, run_id, blogger_ids)
            repository.finish_run(run_id, success_count=success_count, failed_count=failed_count)
        finally:
            repository.close()
    except RuntimeError as error:
        if "Missing MySQL driver" not in str(error):
            raise
        repository = MySQLCliRepository(config["mysql"], project_root)
        repository.write(bloggers, snapshots, crawl_month)
    print(f"已写入 MySQL：{len(snapshots)} 条快照")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.login:
            return run_login(args.config)
        if args.backup:
            return run_backup(args.config)
        if args.reset_month:
            return run_reset_month(args.config, args.reset_month, args.yes)
        if args.report:
            return run_report(args.config, args.month)
        if args.analyze:
            return run_analyze(args.config, args.month, args.prev_month)
        if args.export_bi:
            return run_export_bi(args.config)
        return run(
            args.config,
            args.dry_run,
            args.month,
            resume=args.resume,
            retry_failed=args.retry_failed,
        )
    except CheckpointError as error:
        print(f"断点错误：{error}", file=sys.stderr)
        return 2
    except ConfigError as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2
    except CollectorNotConfigured as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2
    except (BrowserAutomationUnavailable, LoginUrlNotConfigured, LoginTimeout) as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
