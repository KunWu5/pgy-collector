from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .web_collector import CollectorNotConfigured, validate_source_config


class VerificationCodeRequired(RuntimeError):
    pass


def _session_path(config: dict[str, dict[str, str]], project_root: Path) -> Path:
    configured_path = config.get("source", {}).get("session_path") or ".session/session.json"
    path = Path(configured_path)
    return path if path.is_absolute() else project_root / path


def prepare_login_session(
    config: dict[str, dict[str, str]],
    project_root: Path,
    verification_code: str | None,
) -> Path:
    source_config = config.get("source")
    validate_source_config(source_config)

    code = (verification_code or "").strip()
    if not code:
        raise VerificationCodeRequired("请输入短信验证码。")

    session_path = _session_path(config, project_root)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "username": source_config["username"].strip() if source_config else "",
        "status": "verification_code_collected",
        "verification_code_received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "next_step": "implement_browser_login",
        "note": "这里不保存密码或短信验证码；后续真实网页登录成功后会替换为浏览器登录态。",
    }
    session_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return session_path
