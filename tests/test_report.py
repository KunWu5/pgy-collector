import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from helpers import workspace_tempdir
from blogger_crawler.models import Snapshot
from blogger_crawler.report import build_change_rows, export_monthly_report


def make_snapshot(
    red_id="report_001",
    month="2026-08",
    *,
    fans=100,
    exposure=1000,
    status="success",
):
    return Snapshot(
        red_id=red_id,
        crawl_month=month,
        nickname="报表博主",
        fans_count=fans,
        image_price=Decimal("100.00"),
        video_price=Decimal("200.00"),
        tags=[],
        note_count_30d=10,
        exposure_median_30d=exposure,
        read_median_30d=100,
        interaction_median_30d=20,
        note_count_90d=30,
        exposure_median_90d=3000,
        read_median_90d=300,
        interaction_median_90d=60,
        crawl_status=status,
        error_message=None if status == "success" else "failed",
        crawled_at=datetime(2026, 8, 5, 10, 0, 0),
    )


class ReportTest(unittest.TestCase):
    def test_build_change_rows_calculates_deltas_and_alerts(self):
        current = make_snapshot(fans=140, exposure=1500)
        previous = make_snapshot(month="2026-07", fans=100, exposure=1000)
        failed = make_snapshot(red_id="failed_report", status="failed")

        rows = build_change_rows([current, failed], [previous], threshold_percent=30)
        fans_row = next(row for row in rows if row["metric_key"] == "fans_count")
        exposure_row = next(row for row in rows if row["metric_key"] == "exposure_median_30d")

        self.assertEqual(fans_row["delta"], 40)
        self.assertEqual(fans_row["change_percent"], 40.0)
        self.assertTrue(fans_row["is_alert"])
        self.assertEqual(exposure_row["status"], "异常波动")
        self.assertFalse(any(row["red_id"] == "failed_report" for row in rows))

    def test_build_change_rows_marks_missing_previous_month_without_alert(self):
        rows = build_change_rows([make_snapshot()], [], threshold_percent=30)

        self.assertTrue(rows)
        self.assertTrue(all(row["status"] == "无上月数据" for row in rows))
        self.assertFalse(any(row["is_alert"] for row in rows))

    def test_export_monthly_report_creates_change_and_alert_sheets(self):
        rows = build_change_rows(
            [make_snapshot(fans=140)],
            [make_snapshot(month="2026-07")],
            threshold_percent=30,
        )
        alerts = [row for row in rows if row["is_alert"]]

        with workspace_tempdir() as tmp:
            path = export_monthly_report(rows, alerts, Path(tmp) / "report.xlsx")
            workbook = load_workbook(path, read_only=True)

        self.assertEqual(workbook.sheetnames, ["月度变化", "异常提醒"])
        self.assertEqual(workbook["月度变化"].max_row, len(rows) + 1)
        self.assertEqual(workbook["异常提醒"].max_row, len(alerts) + 1)
        self.assertEqual(workbook["月度变化"].cell(1, 1).value, "博主ID")


if __name__ == "__main__":
    unittest.main()
