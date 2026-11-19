import unittest
from pathlib import Path

from openpyxl import Workbook

from blogger_crawler.importer import load_bloggers
from helpers import workspace_tempdir


class ImporterTest(unittest.TestCase):
    def test_loads_english_header_workbook(self):
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "bloggers.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "blogger_list"
            worksheet.append(["red_id", "nickname", "group_name", "remark"])
            worksheet.append(["test_001", "测试A", "美妆", "重点"])
            worksheet.append(["", "", "", ""])
            workbook.save(path)

            bloggers = load_bloggers(path)

        self.assertEqual(len(bloggers), 1)
        self.assertEqual(bloggers[0].red_id, "test_001")
        self.assertEqual(bloggers[0].nickname, "测试A")

    def test_rejects_duplicate_red_id(self):
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "bloggers.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(["博主ID", "昵称备注"])
            worksheet.append(["same_id", "A"])
            worksheet.append(["same_id", "B"])
            workbook.save(path)

            with self.assertRaisesRegex(ValueError, "Duplicate red_id"):
                load_bloggers(path)

    def test_rejects_a_workbook_without_any_bloggers(self):
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "bloggers.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(["博主ID", "昵称备注"])
            workbook.save(path)

            with self.assertRaisesRegex(ValueError, "empty"):
                load_bloggers(path)

    def test_rejects_duplicate_red_ids_ignoring_case(self):
        with workspace_tempdir() as tmp:
            path = Path(tmp) / "bloggers.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(["博主ID", "昵称备注"])
            worksheet.append(["IrisDaily", "A"])
            worksheet.append(["irisdaily", "B"])
            workbook.save(path)

            with self.assertRaisesRegex(ValueError, "Duplicate red_id"):
                load_bloggers(path)


if __name__ == "__main__":
    unittest.main()
