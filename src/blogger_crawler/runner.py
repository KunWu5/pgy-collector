from collections.abc import Callable, Iterable
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .checkpoint import CheckpointError, load_checkpoint, save_checkpoint
from .models import Blogger, Snapshot
from .web_collector import SessionExpired


Collector = Callable[[Blogger, str], Snapshot]


def failed_snapshot(blogger: Blogger, crawl_month: str, error: Exception) -> Snapshot:
    return Snapshot(
        red_id=blogger.red_id,
        crawl_month=crawl_month,
        nickname=blogger.nickname or f"Unknown-{blogger.red_id}",
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
        error_message=str(error),
        crawled_at=datetime.now(),
    )


def collect_snapshots(
    bloggers: Iterable[Blogger],
    crawl_month: str,
    collector: Collector,
    log_path: str | Path,
    retry_count: int = 0,
    checkpoint_path: str | Path | None = None,
    resume: bool = False,
    retry_failed: bool = False,
) -> list[Snapshot]:
    if retry_count < 0:
        raise ValueError("retry_count cannot be negative.")
    if resume and retry_failed:
        raise ValueError("resume and retry_failed cannot both be enabled.")

    blogger_list = list(bloggers)
    current_ids = {blogger.red_id for blogger in blogger_list}
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    if (resume or retry_failed) and checkpoint is None:
        raise CheckpointError("A checkpoint path is required for resume or failed-only retry.")
    if (resume or retry_failed) and checkpoint is not None and not checkpoint.exists():
        raise CheckpointError(f"Checkpoint file not found: {checkpoint}")

    prior_snapshots = load_checkpoint(checkpoint) if (resume or retry_failed) and checkpoint else []
    stored_by_id = {
        snapshot.red_id: snapshot
        for snapshot in prior_snapshots
        if snapshot.red_id in current_ids and snapshot.crawl_month == crawl_month
    }
    if not resume and not retry_failed and checkpoint is not None and checkpoint.exists():
        checkpoint.unlink()

    if retry_failed:
        failed_ids = {
            red_id
            for red_id, snapshot in stored_by_id.items()
            if snapshot.crawl_status == "failed"
        }
        if not failed_ids:
            raise CheckpointError("No failed blogger exists in the checkpoint.")
        target_bloggers = [blogger for blogger in blogger_list if blogger.red_id in failed_ids]
        run_label = "RETRY_FAILED"
    elif resume:
        target_bloggers = [
            blogger
            for blogger in blogger_list
            if (
                blogger.red_id not in stored_by_id
                or stored_by_id[blogger.red_id].crawl_status != "success"
            )
        ]
        run_label = "RESUME"
    else:
        target_bloggers = blogger_list
        run_label = "RUN"

    log_lines = [
        f"{run_label} month={crawl_month} started_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    output_path = Path(log_path)
    written_lines = 0

    def write_log() -> None:
        # 增量追加：首次写入截断旧日志，之后只写新增行，避免整批重写。
        nonlocal written_lines
        pending = log_lines[written_lines:]
        if not pending:
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if written_lines == 0 else "a"
        with output_path.open(mode, encoding="utf-8") as handle:
            for line in pending:
                handle.write(f"{line}\n")
        written_lines = len(log_lines)

    def ordered_snapshots() -> list[Snapshot]:
        return [
            stored_by_id[blogger.red_id]
            for blogger in blogger_list
            if blogger.red_id in stored_by_id
        ]

    def save_progress() -> None:
        if checkpoint is not None:
            save_checkpoint(checkpoint, ordered_snapshots())

    write_log()

    managed_collector = (
        collector
        if hasattr(collector, "__enter__") and hasattr(collector, "__exit__")
        else nullcontext(collector)
    )
    if target_bloggers:
        with managed_collector as active_collector:
            for blogger in target_bloggers:
                last_error: Exception | None = None
                for attempt in range(retry_count + 1):
                    try:
                        snapshot = active_collector(blogger, crawl_month)
                        stored_by_id[blogger.red_id] = snapshot
                        log_lines.append(f"SUCCESS {blogger.red_id} {snapshot.nickname}")
                        save_progress()
                        write_log()
                        break
                    except SessionExpired as error:
                        log_lines.append(
                            f"ABORT {blogger.red_id} session_expired error={error}"
                        )
                        write_log()
                        raise
                    except Exception as error:
                        last_error = error
                        if attempt < retry_count:
                            log_lines.append(
                                f"RETRY {blogger.red_id} attempt={attempt + 2}/{retry_count + 1} "
                                f"error={error}"
                            )
                            write_log()
                else:
                    snapshot = failed_snapshot(
                        blogger,
                        crawl_month,
                        last_error or RuntimeError("unknown collection error"),
                    )
                    stored_by_id[blogger.red_id] = snapshot
                    log_lines.append(
                        f"FAILED {blogger.red_id} {snapshot.nickname} {snapshot.error_message}"
                    )
                    save_progress()
                    write_log()

    snapshots = ordered_snapshots()
    success_count = sum(1 for snapshot in snapshots if snapshot.crawl_status == "success")
    failed_count = len(snapshots) - success_count
    log_lines.append(f"SUMMARY total={len(snapshots)} success={success_count} failed={failed_count}")
    log_lines.append(f"RUN finished_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if checkpoint is not None:
        if (
            len(snapshots) == len(blogger_list)
            and success_count == len(blogger_list)
        ):
            checkpoint.unlink(missing_ok=True)
        else:
            save_progress()
    write_log()
    return snapshots
