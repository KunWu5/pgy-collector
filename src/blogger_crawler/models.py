from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Blogger:
    red_id: str
    nickname: str | None = None
    group_name: str | None = None
    remark: str | None = None


@dataclass(frozen=True)
class Snapshot:
    red_id: str
    crawl_month: str
    nickname: str
    fans_count: int
    image_price: Decimal
    video_price: Decimal
    tags: list[str]
    note_count_30d: int
    exposure_median_30d: int
    read_median_30d: int
    interaction_median_30d: int
    note_count_90d: int | None
    exposure_median_90d: int | None
    read_median_90d: int | None
    interaction_median_90d: int | None
    crawl_status: str
    error_message: str | None
    crawled_at: datetime
