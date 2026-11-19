from pathlib import Path

from .mock_collector import collect_mock_snapshot
from .browser_session import BrowserSession
from .web_collector import validate_session
from .runner import Collector


def build_collector(
    config: dict[str, dict[str, str]],
    project_root: Path | None = None,
) -> Collector:
    mode = config.get("run", {}).get("mode", "mock").strip().lower()
    if mode == "mock":
        return collect_mock_snapshot
    if mode == "real":
        root = project_root or Path.cwd()
        validate_session(config.get("source"), root)
        return BrowserSession(config, root)
    raise ValueError("Unsupported run.mode. Use 'mock' or 'real'.")
