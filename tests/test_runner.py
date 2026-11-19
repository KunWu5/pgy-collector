import unittest
from decimal import Decimal
from pathlib import Path

from helpers import workspace_tempdir
from blogger_crawler.checkpoint import save_checkpoint
from blogger_crawler.models import Blogger, Snapshot
from blogger_crawler.web_collector import SessionExpired
from blogger_crawler.runner import collect_snapshots, failed_snapshot


def success_snapshot(blogger, crawl_month):
    return Snapshot(
        red_id=blogger.red_id,
        crawl_month=crawl_month,
        nickname=blogger.nickname,
        fans_count=100,
        image_price=Decimal("10.00"),
        video_price=Decimal("20.00"),
        tags=[],
        note_count_30d=1,
        exposure_median_30d=2,
        read_median_30d=3,
        interaction_median_30d=4,
        note_count_90d=None,
        exposure_median_90d=None,
        read_median_90d=None,
        interaction_median_90d=None,
        crawl_status="success",
        error_message=None,
        crawled_at=None,
    )


class RunnerTest(unittest.TestCase):
    def test_collect_snapshots_aborts_batch_when_session_expires(self):
        bloggers = [
            Blogger(red_id="expired_001", nickname="登录失效博主"),
            Blogger(red_id="never_002", nickname="不应继续博主"),
        ]
        attempted = []

        def collector(blogger, crawl_month):
            attempted.append(blogger.red_id)
            raise SessionExpired("登录态已失效，请重新运行 --login。")

        with workspace_tempdir() as tmp:
            log_path = Path(tmp) / "run.log"
            with self.assertRaises(SessionExpired):
                collect_snapshots(
                    bloggers,
                    "2026-08",
                    collector,
                    log_path,
                    retry_count=2,
                )

        self.assertEqual(attempted, ["expired_001"])

    def test_resume_skips_success_and_retries_failed_bloggers(self):
        bloggers = [
            Blogger(red_id="done_001", nickname="已完成"),
            Blogger(red_id="failed_001", nickname="待重试"),
        ]
        prior_failed = failed_snapshot(bloggers[1], "2026-08", RuntimeError("temporary"))

        with workspace_tempdir() as tmp:
            checkpoint_path = Path(tmp) / "checkpoint.json"
            save_checkpoint(
                checkpoint_path,
                [success_snapshot(bloggers[0], "2026-08"), prior_failed],
            )
            attempted = []

            def collector(blogger, crawl_month):
                attempted.append(blogger.red_id)
                return success_snapshot(blogger, crawl_month)

            snapshots = collect_snapshots(
                bloggers,
                "2026-08",
                collector,
                Path(tmp) / "run.log",
                checkpoint_path=checkpoint_path,
                resume=True,
            )

        self.assertEqual(attempted, ["failed_001"])
        self.assertEqual([snapshot.crawl_status for snapshot in snapshots], ["success", "success"])
        self.assertFalse(checkpoint_path.exists())

    def test_retry_failed_processes_only_failed_checkpoint_rows(self):
        bloggers = [
            Blogger(red_id="done_002", nickname="已完成"),
            Blogger(red_id="failed_002", nickname="待重试"),
        ]
        prior_failed = failed_snapshot(bloggers[1], "2026-08", RuntimeError("temporary"))

        with workspace_tempdir() as tmp:
            checkpoint_path = Path(tmp) / "checkpoint.json"
            save_checkpoint(
                checkpoint_path,
                [success_snapshot(bloggers[0], "2026-08"), prior_failed],
            )
            attempted = []

            def collector(blogger, crawl_month):
                attempted.append(blogger.red_id)
                return success_snapshot(blogger, crawl_month)

            collect_snapshots(
                bloggers,
                "2026-08",
                collector,
                Path(tmp) / "run.log",
                checkpoint_path=checkpoint_path,
                retry_failed=True,
            )

        self.assertEqual(attempted, ["failed_002"])
        self.assertFalse(checkpoint_path.exists())

    def test_collect_snapshots_enters_and_closes_a_managed_collector(self):
        blogger = Blogger(red_id="managed_001", nickname="托管采集器")
        events = []

        class ManagedCollector:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                events.append("exit")

            def __call__(self, current_blogger, crawl_month):
                events.append(current_blogger.red_id)
                return Snapshot(
                    red_id=current_blogger.red_id,
                    crawl_month=crawl_month,
                    nickname=current_blogger.nickname,
                    fans_count=100,
                    image_price=Decimal("10.00"),
                    video_price=Decimal("20.00"),
                    tags=[],
                    note_count_30d=1,
                    exposure_median_30d=2,
                    read_median_30d=3,
                    interaction_median_30d=4,
                    note_count_90d=None,
                    exposure_median_90d=None,
                    read_median_90d=None,
                    interaction_median_90d=None,
                    crawl_status="success",
                    error_message=None,
                    crawled_at=None,
                )

        with workspace_tempdir() as tmp:
            snapshots = collect_snapshots(
                [blogger],
                "2026-07",
                ManagedCollector(),
                Path(tmp) / "run.log",
            )

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(events, ["enter", "managed_001", "exit"])

    def test_collect_snapshots_records_failures_and_writes_log(self):
        bloggers = [
            Blogger(red_id="ok_001", nickname="成功博主"),
            Blogger(red_id="bad_001", nickname="失败博主"),
        ]

        def collector(blogger, crawl_month):
            if blogger.red_id == "bad_001":
                raise RuntimeError("登录态失效")
            return Snapshot(
                red_id=blogger.red_id,
                crawl_month=crawl_month,
                nickname=blogger.nickname,
                fans_count=100,
                image_price=Decimal("10.00"),
                video_price=Decimal("20.00"),
                tags=["beauty"],
                note_count_30d=1,
                exposure_median_30d=2,
                read_median_30d=3,
                interaction_median_30d=4,
                note_count_90d=None,
                exposure_median_90d=None,
                read_median_90d=None,
                interaction_median_90d=None,
                crawl_status="success",
                error_message=None,
                crawled_at=None,
            )

        with workspace_tempdir() as tmp:
            log_path = Path(tmp) / "run.log"
            snapshots = collect_snapshots(bloggers, "2026-07", collector, log_path)
            log_text = log_path.read_text(encoding="utf-8")

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].crawl_status, "success")
        self.assertEqual(snapshots[1].red_id, "bad_001")
        self.assertEqual(snapshots[1].nickname, "失败博主")
        self.assertEqual(snapshots[1].crawl_status, "failed")
        self.assertIn("登录态失效", snapshots[1].error_message)
        self.assertEqual(snapshots[1].fans_count, 0)
        self.assertIn("total=2 success=1 failed=1", log_text)
        self.assertIn("SUCCESS ok_001 成功博主", log_text)
        self.assertIn("FAILED bad_001 失败博主 登录态失效", log_text)

    def test_collect_snapshots_retries_a_transient_failure(self):
        blogger = Blogger(red_id="retry_001", nickname="重试博主")
        attempts = {"count": 0}

        def collector(current_blogger, crawl_month):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("临时网络错误")
            return Snapshot(
                red_id=current_blogger.red_id,
                crawl_month=crawl_month,
                nickname=current_blogger.nickname,
                fans_count=100,
                image_price=Decimal("10.00"),
                video_price=Decimal("20.00"),
                tags=[],
                note_count_30d=1,
                exposure_median_30d=2,
                read_median_30d=3,
                interaction_median_30d=4,
                note_count_90d=None,
                exposure_median_90d=None,
                read_median_90d=None,
                interaction_median_90d=None,
                crawl_status="success",
                error_message=None,
                crawled_at=None,
            )

        with workspace_tempdir() as tmp:
            log_path = Path(tmp) / "run.log"
            snapshots = collect_snapshots(
                [blogger],
                "2026-07",
                collector,
                log_path,
                retry_count=2,
            )
            log_text = log_path.read_text(encoding="utf-8")

        self.assertEqual(attempts["count"], 3)
        self.assertEqual(snapshots[0].crawl_status, "success")
        self.assertIn("RETRY retry_001 attempt=2/3", log_text)


if __name__ == "__main__":
    unittest.main()
