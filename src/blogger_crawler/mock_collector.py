from datetime import datetime
from decimal import Decimal
from hashlib import sha256

from .models import Blogger, Snapshot


TAG_POOL = ["beauty", "fashion", "mom_baby", "food", "travel", "lifestyle"]


def _seed(red_id: str) -> int:
    return int(sha256(red_id.encode("utf-8")).hexdigest()[:12], 16)


def collect_mock_snapshot(blogger: Blogger, crawl_month: str) -> Snapshot:
    seed = _seed(blogger.red_id)
    fans_count = 10_000 + seed % 900_000
    note_count_30d = 1 + seed % 30
    exposure_median_30d = 5_000 + seed % 200_000
    read_median_30d = max(1_000, int(exposure_median_30d * 0.62))
    interaction_median_30d = max(100, int(read_median_30d * 0.08))
    image_price = Decimal(800 + seed % 20_000).quantize(Decimal("0.01"))
    video_price = Decimal(1500 + seed % 45_000).quantize(Decimal("0.01"))
    first_tag = TAG_POOL[seed % len(TAG_POOL)]
    second_tag = TAG_POOL[(seed // 7) % len(TAG_POOL)]
    tags = [first_tag] if first_tag == second_tag else [first_tag, second_tag]

    return Snapshot(
        red_id=blogger.red_id,
        crawl_month=crawl_month,
        nickname=blogger.nickname or f"Mock-{blogger.red_id}",
        fans_count=fans_count,
        image_price=image_price,
        video_price=video_price,
        tags=tags,
        note_count_30d=note_count_30d,
        exposure_median_30d=exposure_median_30d,
        read_median_30d=read_median_30d,
        interaction_median_30d=interaction_median_30d,
        note_count_90d=None,
        exposure_median_90d=None,
        read_median_90d=None,
        interaction_median_90d=None,
        crawl_status="success",
        error_message=None,
        crawled_at=datetime.now(),
    )
