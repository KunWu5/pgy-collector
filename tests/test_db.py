import unittest
from datetime import datetime
from decimal import Decimal

from blogger_crawler.db import MySQLRepository, SNAPSHOT_UPSERT_SQL


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 2
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1


class DbTest(unittest.TestCase):
    def test_connector_upsert_updates_all_90_day_fields(self):
        for field in [
            "note_count_90d",
            "exposure_median_90d",
            "read_median_90d",
            "interaction_median_90d",
        ]:
            self.assertIn(f"{field} = VALUES({field})", SNAPSHOT_UPSERT_SQL)

    def test_deactivate_missing_bloggers_uses_parameterized_red_ids(self):
        repository = object.__new__(MySQLRepository)
        connection = FakeConnection()
        repository.connection = connection

        changed = repository.deactivate_missing_bloggers(["keep_001", "keep_002"])

        self.assertEqual(changed, 2)
        sql, params = connection.cursor_instance.calls[0]
        self.assertIn("UPDATE bloggers", sql)
        self.assertIn("status = 'inactive'", sql)
        self.assertIn("red_id NOT IN (%s, %s)", sql)
        self.assertEqual(params, ("keep_001", "keep_002"))
        self.assertEqual(connection.commit_count, 1)

    def test_deactivate_missing_bloggers_rejects_empty_roster(self):
        repository = object.__new__(MySQLRepository)
        repository.connection = FakeConnection()

        with self.assertRaisesRegex(ValueError, "empty"):
            repository.deactivate_missing_bloggers([])

    def test_get_snapshots_for_month_maps_database_rows(self):
        repository = object.__new__(MySQLRepository)
        connection = FakeConnection()
        connection.cursor_instance.rows = [
            (
                "report_001",
                "2026-08",
                "报表博主",
                100,
                Decimal("100.00"),
                Decimal("200.00"),
                '["护肤"]',
                10,
                1000,
                100,
                20,
                30,
                3000,
                300,
                60,
                "success",
                None,
                datetime(2026, 8, 5, 10, 0, 0),
            )
        ]
        repository.connection = connection

        snapshots = repository.get_snapshots_for_month("2026-08")

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].red_id, "report_001")
        self.assertEqual(snapshots[0].tags, ["护肤"])
        self.assertEqual(snapshots[0].note_count_90d, 30)
        self.assertEqual(connection.cursor_instance.calls[0][1], ("2026-08",))


if __name__ == "__main__":
    unittest.main()
