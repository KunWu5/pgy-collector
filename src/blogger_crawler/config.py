import os
from collections.abc import Mapping
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a configured runtime secret cannot be resolved."""


def resolve_config_secrets(
    config: dict[str, dict[str, str]],
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    environment = os.environ if environ is None else environ
    resolved = {
        section_name: dict(section_values)
        for section_name, section_values in config.items()
    }

    _resolve_secret(resolved, "mysql", "password", environment)
    _resolve_secret(resolved, "source", "username", environment)
    _resolve_secret(resolved, "source", "password", environment)
    return resolved


def _resolve_secret(
    config: dict[str, dict[str, str]],
    section_name: str,
    value_key: str,
    environment: Mapping[str, str],
) -> None:
    section = config.get(section_name)
    if section is None:
        return
    env_name = section.get(f"{value_key}_env", "").strip()
    if not env_name:
        return

    value = environment.get(env_name, "")
    if not value:
        raise ConfigError(
            f"{section_name}.{value_key} environment variable is missing or empty: "
            f"{env_name}"
        )
    section[value_key] = value


def load_simple_yaml(path: str | Path) -> dict[str, dict[str, str]]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data: dict[str, dict[str, str]] = {}
    section: str | None = None
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            data[section] = {}
            continue
        if section and ":" in stripped:
            key, value = stripped.split(":", 1)
            data[section][key.strip()] = value.strip().strip("'\"")
    return data
