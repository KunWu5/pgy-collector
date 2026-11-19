import unittest
from datetime import datetime
from decimal import Decimal

from blogger_crawler.db_cli import build_clear_month_script, build_mysql_script, sql_quote
from blogger_crawler.schema import build_schema_script
from blogger_crawler.models import Blogger, Snapshot


class DbCliTest(unittest.TestCase):
    def test_sql_quote_escapes_text_for_mysql(self):
        self.assertEqual(sql_quote("O'Reilly\\test"), "'O\\'Reilly\\\\test'")
        self.assertEqual(sql_quote(None), "NULL")

    def test_build_mysql_script_upserts_bloggers_and_snapshots(self):
        bloggers = [Blogger(red_id="xhs_001", nickname="示例A", group_name="美妆", remark="重点")]
        snapshots = [
            Snapshot(
                red_id="xhs_001",
                crawl_month="2026-07",
                nickname="示例A",
                fans_count=12345,
                image_price=Decimal("1000.00"),
                video_price=Decimal("3000.00"),
                tags=["beauty"],
                note_count_30d=2,
                exposure_median_30d=5000,
                read_median_30d=3000,
                interaction_median_30d=200,
                note_count_90d=None,
                exposure_median_90d=None,
                read_median_90d=None,
                interaction_median_90d=None,
                crawl_status="success",
                error_message=None,
                crawled_at=datetime(2026, 7, 28, 10, 0, 0),
            )
        ]

        script = build_mysql_script(bloggers, snapshots, "2026-07", database="custom_db")

        self.assertIn("CREATE DATABASE IF NOT EXISTS `custom_db`", script)
        self.assertIn("USE `custom_db`", script)
        self.assertIn("CREATE TABLE IF NOT EXISTS bloggers", script)
        self.assertIn("CREATE TABLE IF NOT EXISTS crawl_runs", script)
        self.assertIn("CREATE TABLE IF NOT EXISTS blogger_snapshots", script)
        self.assertIn("INSERT INTO bloggers", script)
        self.assertIn("ON DUPLICATE KEY UPDATE", script)
        self.assertIn("INSERT INTO crawl_runs", script)
        self.assertIn("INSERT INTO blogger_snapshots", script)
        self.assertIn("'xhs_001'", script)
        self.assertIn("'[\"beauty\"]'", script)

    def test_build_mysql_script_marks_missing_bloggers_inactive_without_deleting_them(self):
        bloggers = [Blogger(red_id="keep_001", nickname="保留博主")]
        script = build_mysql_script(bloggers, [], "2026-07", database="custom_db")

        self.assertIn(
            "UPDATE bloggers SET status = 'inactive' WHERE red_id NOT IN ('keep_001')",
            script,
        )
        self.assertNotIn("DELETE FROM bloggers", script)

    def test_build_mysql_script_records_partial_run_when_a_snapshot_fails(self):
        blogger = Blogger(red_id="failed_001", nickname="失败博主")
        snapshot = Snapshot(
            red_id="failed_001",
            crawl_month="2026-07",
            nickname="失败博主",
            fans_count=0,
            image_price=Decimal("0.00"),
            video_price=Decimal("0.00"),
            tags=[],
            note_count_30d=0,
            exposure_median_30d=0,
            read_median_30d=0,
            interaction_median_30d=0,
            note_count_90d=None,
            exposure_median_90d=None,
            read_median_90d=None,
            interaction_median_90d=None,
            crawl_status="failed",
            error_message="network",
            crawled_at=datetime(2026, 7, 28, 10, 0, 0),
        )

        script = build_mysql_script([blogger], [snapshot], "2026-07")

        self.assertIn("status = 'partial'", script)

    def test_build_schema_script_rejects_unsafe_database_names(self):
        with self.assertRaisesRegex(ValueError, "Unsafe MySQL identifier"):
            build_schema_script("blogger-data")

    def test_build_clear_month_script_removes_snapshots_and_runs_only(self):
        script = build_clear_month_script("2026-08", database="custom_db")

        self.assertIn("USE `custom_db`", script)
        self.assertIn("DELETE FROM blogger_snapshots", script)
        self.assertIn("DELETE FROM crawl_runs", script)
        self.assertIn("'2026-08'", script)
        self.assertNotIn("DELETE FROM bloggers", script)


if __name__ == "__main__":
    unittest.main()
