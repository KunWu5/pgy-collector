from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .models import Snapshot


CHECKPOINT_VERSION = 1


class CheckpointError(ValueError):
    """Raised when a saved checkpoint cannot be used safely."""


def _serialize_snapshot(snapshot: Snapshot) -> dict[str, Any]:
    data = asdict(snapshot)
    data["image_price"] = str(snapshot.image_price)
    data["video_price"] = str(snapshot.video_price)
    data["crawled_at"] = (
        snapshot.crawled_at.isoformat() if snapshot.crawled_at is not None else None
    )
    return data


def _deserialize_snapshot(data: dict[str, Any]) -> Snapshot:
    try:
        crawled_at = data.get("crawled_at")
        return Snapshot(
            red_id=str(data["red_id"]),
            crawl_month=str(data["crawl_month"]),
            nickname=str(data["nickname"]),
            fans_count=int(data["fans_count"]),
            image_price=Decimal(str(data["image_price"])),
            video_price=Decimal(str(data["video_price"])),
            tags=list(data.get("tags") or []),
            note_count_30d=int(data["note_count_30d"]),
            exposure_median_30d=int(data["exposure_median_30d"]),
            read_median_30d=int(data["read_median_30d"]),
            interaction_median_30d=int(data["interaction_median_30d"]),
            note_count_90d=(
                int(data["note_count_90d"])
                if data.get("note_count_90d") is not None
                else None
            ),
            exposure_median_90d=(
                int(data["exposure_median_90d"])
                if data.get("exposure_median_90d") is not None
                else None
            ),
            read_median_90d=(
                int(data["read_median_90d"])
                if data.get("read_median_90d") is not None
                else None
            ),
            interaction_median_90d=(
                int(data["interaction_median_90d"])
                if data.get("interaction_median_90d") is not None
                else None
            ),
            crawl_status=str(data["crawl_status"]),
            error_message=data.get("error_message"),
            crawled_at=datetime.fromisoformat(crawled_at) if crawled_at else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CheckpointError("Invalid snapshot in checkpoint file.") from error


def save_checkpoint(path: str | Path, snapshots: Iterable[Snapshot]) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CHECKPOINT_VERSION,
        "snapshots": [_serialize_snapshot(snapshot) for snapshot in snapshots],
    }
    temporary_path = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(checkpoint_path)


def load_checkpoint(path: str | Path) -> list[Snapshot]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return []
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if payload.get("version") != CHECKPOINT_VERSION:
            raise CheckpointError("Unsupported checkpoint version.")
        raw_snapshots = payload.get("snapshots")
        if not isinstance(raw_snapshots, list):
            raise CheckpointError("Checkpoint snapshots must be a list.")
        return [_deserialize_snapshot(item) for item in raw_snapshots]
    except json.JSONDecodeError as error:
        raise CheckpointError("Checkpoint file is not valid JSON.") from error
