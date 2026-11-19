import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from blogger_crawler.exporter import export_snapshots
from blogger_crawler.models import Snapshot
from helpers import workspace_tempdir


class ExporterTest(unittest.TestCase):
    def test_exports_red_ids_as_left_aligned_text(self):
        snapshot = Snapshot(
            red_id="672453974",
            crawl_month="2026-08",
            nickname="超爱买的小许",
            fans_count=10000,
            image_price=Decimal("1200.00"),
            video_price=Decimal("3000.00"),
            tags=["beauty"],
            note_count_30d=3,
            exposure_median_30d=5000,
            read_median_30d=3200,
            interaction_median_30d=200,
            note_count_90d=None,
            exposure_median_90d=None,
            read_median_90d=None,
            interaction_median_90d=None,
            crawl_status="success",
            error_message=None,
            crawled_at=datetime(2026, 8, 25, 12, 0, 0),
        )
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "result.xlsx"
            export_snapshots([snapshot], path, data_source="real")
            red_id_cell = load_workbook(path)["采集数据"]["B2"]

        self.assertEqual(red_id_cell.value, "672453974")
        self.assertEqual(red_id_cell.number_format, "@")
        self.assertEqual(red_id_cell.alignment.horizontal, "left")

    def test_exports_real_source_labels_for_real_snapshots(self):
        snapshot = Snapshot(
            red_id="test_001",
            crawl_month="2026-07",
            nickname="测试A",
            fans_count=10000,
            image_price=Decimal("1200.00"),
            video_price=Decimal("3000.00"),
            tags=["beauty"],
            note_count_30d=3,
            exposure_median_30d=5000,
            read_median_30d=3200,
            interaction_median_30d=200,
            note_count_90d=None,
            exposure_median_90d=None,
            read_median_90d=None,
            interaction_median_90d=None,
            crawl_status="success",
            error_message=None,
            crawled_at=datetime(2026, 7, 28, 10, 30, 0),
        )
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "real_result.xlsx"
            export_snapshots([snapshot], path, data_source="real")
            worksheet = load_workbook(path)["采集数据"]
            values = [cell.value for cell in worksheet[2]]

        self.assertEqual(values[3], "真实采集")
        self.assertEqual(values[4], "是")
        self.assertIn("真实采集", values[5])

    def test_exports_chinese_header_workbook(self):
        snapshot = Snapshot(
            red_id="test_001",
            crawl_month="2026-07",
            nickname="测试A",
            fans_count=10000,
            image_price=Decimal("1200.00"),
            video_price=Decimal("3000.00"),
            tags=["beauty"],
            note_count_30d=3,
            exposure_median_30d=5000,
            read_median_30d=3200,
            interaction_median_30d=200,
            note_count_90d=None,
            exposure_median_90d=None,
            read_median_90d=None,
            interaction_median_90d=None,
            crawl_status="success",
            error_message=None,
            crawled_at=datetime(2026, 7, 28, 10, 30, 0),
        )
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "result.xlsx"
            export_snapshots([snapshot], path)
            workbook = load_workbook(path)
            worksheet = workbook["采集数据"]

            headers = [cell.value for cell in worksheet[1]]
            values = [cell.value for cell in worksheet[2]]

        self.assertIn("博主ID", headers)
        self.assertIn("账户名", headers)
        self.assertIn("数据来源", headers)
        self.assertIn("是否真实采集", headers)
        self.assertIn("备注", headers)
        self.assertIn("近30天曝光中位数", headers)
        self.assertEqual(values[1], "test_001")
        self.assertEqual(values[2], "测试A")
        self.assertEqual(values[3], "离线模拟")
        self.assertEqual(values[4], "否")
        self.assertIn("模拟数据", values[5])


if __name__ == "__main__":
    unittest.main()
