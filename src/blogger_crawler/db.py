from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .models import Blogger, Snapshot
from .schema import build_schema_statements


def require_mysql_connector():
    try:
        import mysql.connector  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing MySQL driver. Install it with: pip install mysql-connector-python"
        ) from exc
    return mysql.connector


def snapshot_to_db_row(snapshot: Snapshot) -> dict[str, object]:
    row = asdict(snapshot)
    row["image_price"] = str(snapshot.image_price)
    row["video_price"] = str(snapshot.video_price)
    row["tags"] = json.dumps(snapshot.tags, ensure_ascii=False)
    row["crawled_at"] = snapshot.crawled_at.strftime("%Y-%m-%d %H:%M:%S")
    return row


def decimal_or_none(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


SNAPSHOT_UPSERT_SQL = """
INSERT INTO blogger_snapshots (
  crawl_run_id, blogger_id, red_id, crawl_month, nickname, fans_count,
  image_price, video_price, tags, note_count_30d, exposure_median_30d,
  read_median_30d, interaction_median_30d, note_count_90d,
  exposure_median_90d, read_median_90d, interaction_median_90d,
  crawl_status, error_message, crawled_at
)
VALUES (
  %(crawl_run_id)s, %(blogger_id)s, %(red_id)s, %(crawl_month)s,
  %(nickname)s, %(fans_count)s, %(image_price)s, %(video_price)s,
  %(tags)s, %(note_count_30d)s, %(exposure_median_30d)s,
  %(read_median_30d)s, %(interaction_median_30d)s, %(note_count_90d)s,
  %(exposure_median_90d)s, %(read_median_90d)s,
  %(interaction_median_90d)s, %(crawl_status)s, %(error_message)s,
  %(crawled_at)s
)
ON DUPLICATE KEY UPDATE
  crawl_run_id = VALUES(crawl_run_id),
  blogger_id = VALUES(blogger_id),
  nickname = VALUES(nickname),
  fans_count = VALUES(fans_count),
  image_price = VALUES(image_price),
  video_price = VALUES(video_price),
  tags = VALUES(tags),
  note_count_30d = VALUES(note_count_30d),
  exposure_median_30d = VALUES(exposure_median_30d),
  read_median_30d = VALUES(read_median_30d),
  interaction_median_30d = VALUES(interaction_median_30d),
  note_count_90d = VALUES(note_count_90d),
  exposure_median_90d = VALUES(exposure_median_90d),
  read_median_90d = VALUES(read_median_90d),
  interaction_median_90d = VALUES(interaction_median_90d),
  crawl_status = VALUES(crawl_status),
  error_message = VALUES(error_message),
  crawled_at = VALUES(crawled_at)
"""


class MySQLRepository:
    def __init__(self, mysql_config: dict[str, str]):
        mysql_connector = require_mysql_connector()
        admin_connection = mysql_connector.connect(
            host=mysql_config["host"],
            port=int(mysql_config.get("port", "3306")),
            user=mysql_config["user"],
            password=mysql_config["password"],
        )
        try:
            with admin_connection.cursor() as cursor:
                for statement in build_schema_statements(mysql_config["database"]):
                    cursor.execute(statement)
            admin_connection.commit()
        finally:
            admin_connection.close()

        self.connection = mysql_connector.connect(
            host=mysql_config["host"],
            port=int(mysql_config.get("port", "3306")),
            database=mysql_config["database"],
            user=mysql_config["user"],
            password=mysql_config["password"],
        )

    def close(self) -> None:
        self.connection.close()

    def upsert_bloggers(self, bloggers: Iterable[Blogger]) -> dict[str, int]:
        sql = """
        INSERT INTO bloggers (red_id, nickname, group_name, remark, status)
        VALUES (%s, %s, %s, %s, 'active')
        ON DUPLICATE KEY UPDATE
          nickname = VALUES(nickname),
          group_name = VALUES(group_name),
          remark = VALUES(remark),
          status = 'active'
        """
        with self.connection.cursor() as cursor:
            for blogger in bloggers:
                cursor.execute(sql, (blogger.red_id, blogger.nickname, blogger.group_name, blogger.remark))
        self.connection.commit()
        return self.get_blogger_ids()

    def sync_bloggers(self, bloggers: Iterable[Blogger]) -> dict[str, int]:
        blogger_list = list(bloggers)
        if not blogger_list:
            raise ValueError("Cannot synchronize an empty blogger roster.")
        blogger_ids = self.upsert_bloggers(blogger_list)
        self.deactivate_missing_bloggers(blogger.red_id for blogger in blogger_list)
        return blogger_ids

    def deactivate_missing_bloggers(self, current_red_ids: Iterable[str]) -> int:
        red_ids = [str(red_id).strip() for red_id in current_red_ids if str(red_id).strip()]
        if not red_ids:
            raise ValueError("Cannot mark bloggers inactive for an empty roster.")
        placeholders = ", ".join(["%s"] * len(red_ids))
        sql = f"""
        UPDATE bloggers
        SET status = 'inactive'
        WHERE red_id NOT IN ({placeholders})
          AND status <> 'inactive'
        """
        with self.connection.cursor() as cursor:
            cursor.execute(sql, tuple(red_ids))
            changed = cursor.rowcount
        self.connection.commit()
        return int(changed)

    def get_blogger_ids(self) -> dict[str, int]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id, red_id FROM bloggers")
            return {red_id: blogger_id for blogger_id, red_id in cursor.fetchall()}

    def get_snapshots_for_month(self, crawl_month: str) -> list[Snapshot]:
        sql = """
        SELECT red_id, crawl_month, nickname, fans_count, image_price, video_price,
               tags, note_count_30d, exposure_median_30d, read_median_30d,
               interaction_median_30d, note_count_90d, exposure_median_90d,
               read_median_90d, interaction_median_90d, crawl_status,
               error_message, crawled_at
        FROM blogger_snapshots
        WHERE crawl_month = %s
        ORDER BY red_id
        """
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (crawl_month,))
            rows = cursor.fetchall()

        snapshots: list[Snapshot] = []
        for row in rows:
            tags = row[6]
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except json.JSONDecodeError:
                    tags = []
            crawled_at = row[17]
            if isinstance(crawled_at, str):
                crawled_at = datetime.fromisoformat(crawled_at)
            snapshots.append(
                Snapshot(
                    red_id=str(row[0]),
                    crawl_month=str(row[1]),
                    nickname=str(row[2]),
                    fans_count=int(row[3]),
                    image_price=Decimal(str(row[4])),
                    video_price=Decimal(str(row[5])),
                    tags=list(tags or []),
                    note_count_30d=int(row[7]),
                    exposure_median_30d=int(row[8]),
                    read_median_30d=int(row[9]),
                    interaction_median_30d=int(row[10]),
                    note_count_90d=int(row[11]) if row[11] is not None else None,
                    exposure_median_90d=int(row[12]) if row[12] is not None else None,
                    read_median_90d=int(row[13]) if row[13] is not None else None,
                    interaction_median_90d=int(row[14]) if row[14] is not None else None,
                    crawl_status=str(row[15]),
                    error_message=row[16],
                    crawled_at=crawled_at,
                )
            )
        return snapshots

    def create_run(self, run_month: str, total_count: int) -> int:
        sql = """
        INSERT INTO crawl_runs (run_month, total_count, status)
        VALUES (%s, %s, 'running')
        """
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (run_month, total_count))
            run_id = cursor.lastrowid
        self.connection.commit()
        return int(run_id)

    def upsert_snapshots(
        self,
        snapshots: Iterable[Snapshot],
        crawl_run_id: int,
        blogger_ids: dict[str, int],
    ) -> None:
        sql = SNAPSHOT_UPSERT_SQL
        rows = []
        for snapshot in snapshots:
            row = snapshot_to_db_row(snapshot)
            row["crawl_run_id"] = crawl_run_id
            row["blogger_id"] = blogger_ids.get(snapshot.red_id)
            rows.append(row)
        if not rows:
            return
        # executemany 批量写入，减少逐条往返。
        with self.connection.cursor() as cursor:
            cursor.executemany(sql, rows)
        self.connection.commit()

    def finish_run(self, run_id: int, success_count: int, failed_count: int) -> None:
        status = "success" if failed_count == 0 else "partial"
        sql = """
        UPDATE crawl_runs
        SET finished_at = CURRENT_TIMESTAMP,
            success_count = %s,
            failed_count = %s,
            status = %s
        WHERE id = %s
        """
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (success_count, failed_count, status, run_id))
        self.connection.commit()

    def clear_month(self, crawl_month: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM blogger_snapshots WHERE crawl_month = %s",
                (crawl_month,),
            )
            cursor.execute(
                "DELETE FROM crawl_runs WHERE run_month = %s",
                (crawl_month,),
            )
        self.connection.commit()
