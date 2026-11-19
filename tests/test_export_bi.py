# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

from blogger_crawler.export_bi import discover_result_months, export_bi_package
from blogger_crawler.exporter import export_snapshots
from blogger_crawler.models import Snapshot

from test_analysis import make_snapshot


def write_blogger_list(path: Path, red_ids):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "blogger_list"
    sheet.append(["博主ID", "昵称", "分组", "备注"])
    for red_id in red_ids:
        sheet.append([red_id, f"博主{red_id}", "测试组", ""])
    workbook.save(path)


class ExportBiTest(unittest.TestCase):
    def test_export_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_dir = root / "exports"
            export_dir.mkdir()
            current = [
                make_snapshot(red_id="a", video_price="1000.00", exposure=20_000),
                make_snapshot(red_id="b", video_price="2000.00", exposure=10_000),
            ]
            previous = [
                make_snapshot(
                    red_id="a", video_price="1500.00", exposure=20_000, crawl_month="2026-08"
                ),
            ]
            export_snapshots(current, export_dir / "2026-10_real_result.xlsx", data_source="real")
            export_snapshots(previous, export_dir / "2026-08_real_result.xlsx", data_source="real")

            self.assertEqual(discover_result_months(export_dir, "real"), ["2026-08", "2026-10"])

            blogger_list = root / "blogger_list.xlsx"
            write_blogger_list(blogger_list, ["a", "b"])
            out_dir = root / "bi"
            tables = export_bi_package(export_dir, blogger_list, out_dir, "real", 30.0)

            self.assertEqual(
                sorted(tables),
                ["blogger_changes", "blogger_snapshots", "bloggers", "crawl_runs"],
            )
            for path in tables.values():
                self.assertTrue(path.exists())

            snapshots_book = load_workbook(tables["blogger_snapshots"], read_only=True)
            snapshots = snapshots_book["月度快照"]
            rows = list(snapshots.iter_rows(values_only=True))
            snapshots_book.close()
            # 表头 + 8月1条 + 10月2条（月份内按名单顺序 a、b）
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0][0], "采集月份")
            self.assertEqual(rows[1][0], "2026-08")
            self.assertEqual(rows[2][0], "2026-10")
            self.assertEqual(rows[2][1], "a")
            # a 博主 10 月 CPM = 1000/20000*1000 = 50
            self.assertEqual(rows[2][13], 50.0)
            self.assertEqual(rows[3][1], "b")

            changes_book = load_workbook(tables["blogger_changes"], read_only=True)
            changes = changes_book["环比变化"]
            change_rows = list(changes.iter_rows(values_only=True))
            changes_book.close()
            self.assertEqual(len(change_rows), 2)  # 表头 + a 的一条
            self.assertEqual(change_rows[1][1], "2026-10")
            self.assertEqual(change_rows[1][2], "a")

            runs_book = load_workbook(tables["crawl_runs"], read_only=True)
            runs = runs_book["运行记录"]
            run_rows = list(runs.iter_rows(values_only=True))
            runs_book.close()
            self.assertEqual(len(run_rows), 3)  # 表头 + 两个月
            self.assertEqual(run_rows[2][4], "success")

            bloggers_book = load_workbook(tables["bloggers"], read_only=True)
            bloggers = bloggers_book["博主名单"]
            blogger_rows = list(bloggers.iter_rows(values_only=True))
            bloggers_book.close()
            self.assertEqual(len(blogger_rows), 3)

    def test_no_result_files_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_dir = root / "exports"
            export_dir.mkdir()
            blogger_list = root / "blogger_list.xlsx"
            write_blogger_list(blogger_list, ["a"])
            with self.assertRaises(FileNotFoundError):
                export_bi_package(export_dir, blogger_list, root / "bi", "real")


if __name__ == "__main__":
    unittest.main()
