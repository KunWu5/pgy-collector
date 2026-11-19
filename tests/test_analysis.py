# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from blogger_crawler.analysis import (
    analyze_snapshot,
    assign_value_tiers,
    build_analysis,
    build_change_rows,
    classify_fans_tier,
    export_analysis_report,
    load_snapshots_from_result_excel,
)
from blogger_crawler.exporter import export_snapshots
from blogger_crawler.models import Snapshot


def make_snapshot(
    red_id="10001",
    nickname="测试博主",
    fans_count=20_000,
    video_price="1000.00",
    image_price="500.00",
    exposure=10_000,
    read=2_000,
    interaction=100,
    crawl_status="success",
    crawl_month="2026-10",
) -> Snapshot:
    return Snapshot(
        red_id=red_id,
        crawl_month=crawl_month,
        nickname=nickname,
        fans_count=fans_count,
        image_price=Decimal(image_price),
        video_price=Decimal(video_price),
        tags=["护肤", "美妆"],
        note_count_30d=5,
        exposure_median_30d=exposure,
        read_median_30d=read,
        interaction_median_30d=interaction,
        note_count_90d=15,
        exposure_median_90d=30_000,
        read_median_90d=6_000,
        interaction_median_90d=300,
        crawl_status=crawl_status,
        error_message=None,
        crawled_at=datetime(2026, 10, 12, 13, 0, 0),
    )


class ClassifyFansTierTest(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(classify_fans_tier(600_000), "头部(≥50万)")
        self.assertEqual(classify_fans_tier(500_000), "头部(≥50万)")
        self.assertEqual(classify_fans_tier(499_999), "腰部(10-50万)")
        self.assertEqual(classify_fans_tier(100_000), "腰部(10-50万)")
        self.assertEqual(classify_fans_tier(99_999), "初级(1-10万)")
        self.assertEqual(classify_fans_tier(10_000), "初级(1-10万)")
        self.assertEqual(classify_fans_tier(9_999), "KOC(<1万)")
        self.assertEqual(classify_fans_tier(0), "KOC(<1万)")


class AnalyzeSnapshotTest(unittest.TestCase):
    def test_derived_metrics(self):
        row = analyze_snapshot(make_snapshot())
        self.assertEqual(row.cpm_video, Decimal("100.00"))  # 1000/10000*1000
        self.assertEqual(row.cpm_image, Decimal("50.00"))
        self.assertEqual(row.cpe_video, Decimal("10.00"))  # 1000/100
        self.assertEqual(row.cost_per_read, Decimal("0.50"))  # 1000/2000
        self.assertEqual(row.interaction_rate, Decimal("5.00"))  # 100/2000*100
        self.assertEqual(row.fans_tier, "初级(1-10万)")
        self.assertEqual(row.quality_flags, ())
        self.assertTrue(row.rankable)

    def test_zero_exposure_is_flagged_and_not_rankable(self):
        row = analyze_snapshot(make_snapshot(exposure=0))
        self.assertIsNone(row.cpm_video)
        # CPE 只依赖互动数，曝光为 0 不影响
        self.assertEqual(row.cpe_video, Decimal("10.00"))
        self.assertFalse(row.rankable)
        self.assertIn("近30天无合作笔记曝光", row.quality_flags)

    def test_zero_video_price_is_flagged(self):
        row = analyze_snapshot(make_snapshot(video_price="0.00"))
        self.assertFalse(row.rankable)
        self.assertIn("视频报价缺失或为0", row.quality_flags)

    def test_failed_snapshot_is_flagged(self):
        row = analyze_snapshot(make_snapshot(crawl_status="failed"))
        self.assertIn("采集失败", row.quality_flags)

    def test_zero_read_denominator_guarded(self):
        row = analyze_snapshot(make_snapshot(read=0))
        self.assertIsNone(row.cost_per_read)
        self.assertIsNone(row.interaction_rate)
        self.assertIn("近30天阅读中位数为0", row.quality_flags)


class AssignValueTiersTest(unittest.TestCase):
    def test_quartile_tiers(self):
        snapshots = [
            make_snapshot(red_id=str(i), video_price="1000.00", exposure=1000 * (i + 1))
            for i in range(4)
        ]
        rows = assign_value_tiers([analyze_snapshot(s) for s in snapshots])
        tiers = {row.red_id: row.value_tier for row in rows}
        # exposure=1000*(i+1)，CPM 随 i 递减：i=3 的 CPM 最低
        self.assertEqual(tiers["3"], "高性价比")
        self.assertEqual(tiers["2"], "中等偏优")
        self.assertEqual(tiers["1"], "中等")
        self.assertEqual(tiers["0"], "偏高")

    def test_unrankable_has_no_tier(self):
        rows = assign_value_tiers(
            [analyze_snapshot(make_snapshot(exposure=0))]
        )
        self.assertEqual(rows[0].value_tier, "")


class BuildChangeRowsTest(unittest.TestCase):
    def test_premium_alert(self):
        current = [make_snapshot(video_price="1300.00")]
        previous = [make_snapshot(video_price="1000.00", crawl_month="2026-08")]
        rows = build_change_rows(current, previous, threshold_percent=30.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].video_price_change_pct, Decimal("30.00"))
        self.assertEqual(rows[0].interaction_change_pct, Decimal("0.00"))
        self.assertEqual(rows[0].alert, "溢价预警")

    def test_value_improvement_alert(self):
        current = [make_snapshot(interaction=200)]
        previous = [make_snapshot(interaction=100, crawl_month="2026-08")]
        rows = build_change_rows(current, previous, threshold_percent=30.0)
        self.assertEqual(rows[0].alert, "性价比提升")

    def test_fans_change_alert(self):
        current = [make_snapshot(fans_count=30_000)]
        previous = [make_snapshot(fans_count=10_000, crawl_month="2026-08")]
        rows = build_change_rows(current, previous, threshold_percent=30.0)
        self.assertIn("粉丝异动", rows[0].alert)

    def test_no_alert_within_threshold(self):
        current = [make_snapshot(video_price="1100.00")]
        previous = [make_snapshot(video_price="1000.00", crawl_month="2026-08")]
        rows = build_change_rows(current, previous, threshold_percent=30.0)
        self.assertEqual(rows[0].alert, "")

    def test_missing_previous_snapshot_skipped(self):
        rows = build_change_rows([make_snapshot()], [], threshold_percent=30.0)
        self.assertEqual(rows, [])

    def test_zero_previous_denominator_is_none(self):
        current = [make_snapshot(interaction=100)]
        previous = [make_snapshot(interaction=0, crawl_month="2026-08")]
        rows = build_change_rows(current, previous, threshold_percent=30.0)
        self.assertIsNone(rows[0].interaction_change_pct)
        self.assertIsNone(rows[0].divergence_pp)


class ExportAndLoadTest(unittest.TestCase):
    def _run_pipeline(self, changes: bool):
        current = [
            make_snapshot(red_id="a", video_price="1000.00", exposure=20_000),
            make_snapshot(red_id="b", video_price="2000.00", exposure=10_000),
            make_snapshot(red_id="c", video_price="500.00", exposure=0),
        ]
        previous = [
            make_snapshot(red_id="a", video_price="1500.00", exposure=20_000, crawl_month="2026-08"),
        ] if changes else []
        analyses = build_analysis(current)
        change_rows = build_change_rows(current, previous, threshold_percent=30.0)
        return analyses, change_rows, current

    def test_export_report_sheets(self):
        analyses, changes, _ = self._run_pipeline(changes=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-10_analysis.xlsx"
            export_analysis_report(analyses, changes, path, "2026-10", "2026-08")
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True)
            self.assertEqual(
                workbook.sheetnames,
                ["摘要", "分析总览", "性价比榜单", "环比与溢价预警"],
            )
            ranking = workbook["性价比榜单"]
            rows = list(ranking.iter_rows(values_only=True))
            self.assertEqual(rows[0][0], "排名")
            # a 的 CPM=50，b 的 CPM=200，榜单按 CPM 升序
            self.assertEqual(rows[1][2], "测试博主")
            self.assertEqual(rows[2][1], "b")
            self.assertEqual(len(rows), 3)  # c 无曝光不进榜单
            workbook.close()

    def test_result_excel_roundtrip(self):
        _, _, current = self._run_pipeline(changes=False)
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "2026-10_real_result.xlsx"
            export_snapshots(current, result_path, data_source="real")
            loaded = load_snapshots_from_result_excel(result_path)
            self.assertEqual(len(loaded), 3)
            by_id = {snapshot.red_id: snapshot for snapshot in loaded}
            self.assertEqual(by_id["a"].fans_count, 20_000)
            self.assertEqual(by_id["a"].video_price, Decimal("1000.00"))
            self.assertEqual(by_id["a"].exposure_median_30d, 20_000)
            self.assertEqual(by_id["a"].interaction_median_30d, 100)
            self.assertEqual(by_id["a"].tags, ["护肤", "美妆"])
            self.assertEqual(by_id["a"].crawl_status, "success")
            self.assertEqual(by_id["a"].crawled_at, datetime(2026, 10, 12, 13, 0, 0))
            self.assertEqual(by_id["c"].note_count_90d, 15)


if __name__ == "__main__":
    unittest.main()
