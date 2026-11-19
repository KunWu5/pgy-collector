from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


COMMON_MYSQLDUMP_CLIENTS = [
    Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Workbench 8.0\mysqldump.exe"),
]


def build_mysqldump_command(
    client_path: Path,
    defaults_file: Path,
    output_path: Path,
    database: str,
) -> list[str]:
    return [
        str(client_path),
        f"--defaults-extra-file={defaults_file}",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--default-character-set=utf8mb4",
        f"--result-file={output_path}",
        database,
    ]


def find_mysqldump(configured_path: str | None = None) -> Path:
    candidates = [Path(configured_path)] if configured_path else []
    candidates.extend(COMMON_MYSQLDUMP_CLIENTS)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "mysqldump.exe not found. Add mysql.dump_path to config.yaml."
    )


def backup_mysql(
    mysql_config: dict[str, str],
    project_root: Path,
    output_dir: Path | None = None,
) -> Path:
    database = mysql_config["database"]
    backup_directory = output_dir or project_root / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = backup_directory / f"{database}_{timestamp}.sql"
    client_path = find_mysqldump(mysql_config.get("dump_path"))

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".cnf",
        prefix="mysqldump_",
        delete=False,
    ) as defaults_handle:
        defaults_handle.write(
            "\n".join(
                [
                    "[client]",
                    f"host={mysql_config['host']}",
                    f"port={mysql_config.get('port', '3306')}",
                    f"user={mysql_config['user']}",
                    f"password={mysql_config['password']}",
                    "",
                ]
            )
        )
        defaults_file = Path(defaults_handle.name)

    try:
        process = subprocess.run(
            build_mysqldump_command(client_path, defaults_file, output_path, database),
            capture_output=True,
            cwd=project_root,
            check=False,
        )
    finally:
        defaults_file.unlink(missing_ok=True)

    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="replace").strip()
        stdout = process.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or stdout or "mysqldump failed")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"MySQL backup file was not created: {output_path}")
    return output_path
