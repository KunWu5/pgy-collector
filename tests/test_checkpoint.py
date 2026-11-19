import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from helpers import workspace_tempdir
from blogger_crawler.checkpoint import load_checkpoint, save_checkpoint
from blogger_crawler.models import Snapshot


class CheckpointTest(unittest.TestCase):
    def test_round_trips_snapshot_values_without_loss(self):
        snapshot = Snapshot(
            red_id="resume_001",
            crawl_month="2026-08",
            nickname="断点博主",
            fans_count=12345,
            image_price=Decimal("123.45"),
            video_price=Decimal("678.90"),
            tags=["护肤", "测评"],
            note_count_30d=3,
            exposure_median_30d=4567,
            read_median_30d=890,
            interaction_median_30d=67,
            note_count_90d=None,
            exposure_median_90d=None,
            read_median_90d=None,
            interaction_median_90d=None,
            crawl_status="failed",
            error_message="临时网络错误",
            crawled_at=datetime(2026, 8, 5, 12, 34, 56),
        )

        with workspace_tempdir() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(path, [snapshot])
            restored = load_checkpoint(path)

        self.assertEqual(restored, [snapshot])

    def test_missing_checkpoint_returns_empty_list(self):
        with workspace_tempdir() as tmp:
            self.assertEqual(load_checkpoint(Path(tmp) / "missing.json"), [])


if __name__ == "__main__":
    unittest.main()
