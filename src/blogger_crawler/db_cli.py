from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .models import Blogger, Snapshot
from .schema import build_schema_script


COMMON_MYSQL_CLIENTS = [
    Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Workbench 8.0\mysql.exe"),
]


def sql_quote(value: object) -> str:
    if value is None:
        return "NULL"
    text = str(value)
    text = text.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def sql_number(value: object) -> str:
    return "NULL" if value is None else str(value)


def build_mysql_script(
    bloggers: Iterable[Blogger],
    snapshots: Iterable[Snapshot],
    crawl_month: str,
    database: str = "blogger_data",
) -> str:
    blogger_list = list(bloggers)
    snapshot_list = list(snapshots)
    if not blogger_list:
        raise ValueError("Cannot synchronize an empty blogger roster.")
    lines = [
        build_schema_script(database),
        "START TRANSACTION;",
    ]
    for blogger in blogger_list:
        lines.append(
            """
INSERT INTO bloggers (red_id, nickname, group_name, remark, status)
VALUES ({red_id}, {nickname}, {group_name}, {remark}, 'active')
ON DUPLICATE KEY UPDATE
  nickname = VALUES(nickname),
  group_name = VALUES(group_name),
  remark = VALUES(remark),
  status = 'active';
""".format(
                red_id=sql_quote(blogger.red_id),
                nickname=sql_quote(blogger.nickname),
                group_name=sql_quote(blogger.group_name),
                remark=sql_quote(blogger.remark),
            ).strip()
        )

    active_red_ids = ", ".join(sql_quote(blogger.red_id) for blogger in blogger_list)
    lines.append(
        "UPDATE bloggers SET status = 'inactive' "
        f"WHERE red_id NOT IN ({active_red_ids}) AND status <> 'inactive';"
    )

    lines.append(
        f"""
INSERT INTO crawl_runs (run_month, total_count, status)
VALUES ({sql_quote(crawl_month)}, {len(blogger_list)}, 'running');
""".strip()
    )
    lines.append("SET @crawl_run_id = LAST_INSERT_ID();")

    for snapshot in snapshot_list:
        tags_json = json.dumps(snapshot.tags, ensure_ascii=False)
        lines.append(
            """
INSERT INTO blogger_snapshots (
  crawl_run_id, blogger_id, red_id, crawl_month, nickname, fans_count,
  image_price, video_price, tags, note_count_30d, exposure_median_30d,
  read_median_30d, interaction_median_30d, note_count_90d,
  exposure_median_90d, read_median_90d, interaction_median_90d,
  crawl_status, error_message, crawled_at
)
VALUES (
  @crawl_run_id,
  (SELECT id FROM bloggers WHERE red_id = {red_id}),
  {red_id},
  {crawl_month},
  {nickname},
  {fans_count},
  {image_price},
  {video_price},
  CAST({tags} AS JSON),
  {note_count_30d},
  {exposure_median_30d},
  {read_median_30d},
  {interaction_median_30d},
  {note_count_90d},
  {exposure_median_90d},
  {read_median_90d},
  {interaction_median_90d},
  {crawl_status},
  {error_message},
  {crawled_at}
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
  crawled_at = VALUES(crawled_at);
""".format(
                red_id=sql_quote(snapshot.red_id),
                crawl_month=sql_quote(snapshot.crawl_month),
                nickname=sql_quote(snapshot.nickname),
                fans_count=sql_number(snapshot.fans_count),
                image_price=sql_number(snapshot.image_price),
                video_price=sql_number(snapshot.video_price),
                tags=sql_quote(tags_json),
                note_count_30d=sql_number(snapshot.note_count_30d),
                exposure_median_30d=sql_number(snapshot.exposure_median_30d),
                read_median_30d=sql_number(snapshot.read_median_30d),
                interaction_median_30d=sql_number(snapshot.interaction_median_30d),
                note_count_90d=sql_number(snapshot.note_count_90d),
                exposure_median_90d=sql_number(snapshot.exposure_median_90d),
                read_median_90d=sql_number(snapshot.read_median_90d),
                interaction_median_90d=sql_number(snapshot.interaction_median_90d),
                crawl_status=sql_quote(snapshot.crawl_status),
                error_message=sql_quote(snapshot.error_message),
                crawled_at=sql_quote(snapshot.crawled_at.strftime("%Y-%m-%d %H:%M:%S")),
            ).strip()
        )

    success_count = sum(1 for snapshot in snapshot_list if snapshot.crawl_status == "success")
    failed_count = len(snapshot_list) - success_count
    run_status = "success" if failed_count == 0 else "partial"
    lines.append(
        f"""
UPDATE crawl_runs
SET finished_at = CURRENT_TIMESTAMP,
    success_count = {success_count},
    failed_count = {failed_count},
    status = {sql_quote(run_status)}
WHERE id = @crawl_run_id;
""".strip()
    )
    lines.extend(["COMMIT;", ""])
    return "\n\n".join(lines)


def build_clear_month_script(month: str, database: str = "blogger_data") -> str:
    if len(month) != 7 or month[4] != "-" or not month.replace("-", "").isdigit():
        raise ValueError(f"Invalid crawl month: {month}")
    return "\n\n".join(
        [
            build_schema_script(database),
            "START TRANSACTION;",
            f"DELETE FROM blogger_snapshots WHERE crawl_month = {sql_quote(month)};",
            f"DELETE FROM crawl_runs WHERE run_month = {sql_quote(month)};",
            "COMMIT;",
            "",
        ]
    )


def find_mysql_client(configured_path: str | None = None) -> Path:
    candidates = [Path(configured_path)] if configured_path else []
    candidates.extend(COMMON_MYSQL_CLIENTS)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("mysql.exe not found. Add mysql.client_path to config.yaml.")


class MySQLCliRepository:
    def __init__(self, mysql_config: dict[str, str], project_root: Path):
        self.mysql_config = mysql_config
        self.project_root = project_root
        self.mysql_client = find_mysql_client(mysql_config.get("client_path"))

    def write(self, bloggers: list[Blogger], snapshots: list[Snapshot], crawl_month: str) -> None:
        script = build_mysql_script(
            bloggers,
            snapshots,
            crawl_month,
            database=self.mysql_config["database"],
        )
        self._run_script(script)

    def clear_month(self, crawl_month: str) -> None:
        script = build_clear_month_script(
            crawl_month,
            database=self.mysql_config["database"],
        )
        self._run_script(script)

    def _run_script(self, script: str) -> None:
        defaults_file = self._write_defaults_file()
        try:
            process = subprocess.run(
                [
                    str(self.mysql_client),
                    f"--defaults-extra-file={defaults_file}",
                    "--default-character-set=utf8mb4",
                    "--batch",
                ],
                input=script.encode("utf-8"),
                capture_output=True,
                cwd=self.project_root,
                check=False,
            )
        finally:
            defaults_file.unlink(missing_ok=True)
        if process.returncode != 0:
            stderr = process.stderr.decode("utf-8", errors="replace").strip()
            stdout = process.stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or stdout)

    def _write_defaults_file(self) -> Path:
        content = "\n".join(
            [
                "[client]",
                f"host={self.mysql_config['host']}",
                f"port={self.mysql_config.get('port', '3306')}",
                f"user={self.mysql_config['user']}",
                f"password={self.mysql_config['password']}",
                "",
            ]
        )
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".cnf",
            prefix="mysql_",
            dir=Path(tempfile.gettempdir()),
            delete=False,
        ) as handle:
            handle.write(content)
            return Path(handle.name)
