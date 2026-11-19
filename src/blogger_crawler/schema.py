import re


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe MySQL identifier: {identifier}")
    return f"`{identifier}`"


def build_schema_script(database: str = "blogger_data") -> str:
    database_name = quote_identifier(database)
    return f"""
CREATE DATABASE IF NOT EXISTS {database_name}
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE {database_name};

CREATE TABLE IF NOT EXISTS bloggers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  red_id VARCHAR(64) NOT NULL,
  nickname VARCHAR(255) NULL,
  group_name VARCHAR(255) NULL,
  remark TEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_bloggers_red_id (red_id),
  KEY idx_bloggers_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS crawl_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_month CHAR(7) NOT NULL,
  total_count INT NOT NULL DEFAULT 0,
  success_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'running',
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_crawl_runs_month (run_month),
  KEY idx_crawl_runs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS blogger_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  crawl_run_id BIGINT UNSIGNED NULL,
  blogger_id BIGINT UNSIGNED NULL,
  red_id VARCHAR(64) NOT NULL,
  crawl_month CHAR(7) NOT NULL,
  nickname VARCHAR(255) NOT NULL,
  fans_count INT NOT NULL DEFAULT 0,
  image_price DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
  video_price DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
  tags JSON NULL,
  note_count_30d INT NOT NULL DEFAULT 0,
  exposure_median_30d INT NOT NULL DEFAULT 0,
  read_median_30d INT NOT NULL DEFAULT 0,
  interaction_median_30d INT NOT NULL DEFAULT 0,
  note_count_90d INT NULL,
  exposure_median_90d INT NULL,
  read_median_90d INT NULL,
  interaction_median_90d INT NULL,
  crawl_status VARCHAR(32) NOT NULL DEFAULT 'success',
  error_message TEXT NULL,
  crawled_at DATETIME NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_snapshots_month_red_id (crawl_month, red_id),
  KEY idx_snapshots_run (crawl_run_id),
  KEY idx_snapshots_blogger (blogger_id),
  CONSTRAINT fk_snapshots_run
    FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_snapshots_blogger
    FOREIGN KEY (blogger_id) REFERENCES bloggers (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
""".strip()


def build_schema_statements(database: str = "blogger_data") -> list[str]:
    return [
        statement.strip()
        for statement in build_schema_script(database).split(";")
        if statement.strip()
    ]
