"""Load, validate, and merge RNM configuration from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from rnm.config.defaults import DEFAULT_CONFIG_PATH
from rnm.config.schema import RNMConfig


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""


def load_config(path: str | Path | None = None) -> RNMConfig:
    """Load and validate an RNM config from a YAML file.

    Args:
        path: Path to YAML config file. Uses default if None.

    Returns:
        Validated RNMConfig instance.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path = config_path.expanduser().resolve()

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config file: {e}") from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}") from e

    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a YAML mapping at the top level")

    try:
        return RNMConfig(**data)
    except ValidationError as e:
        raise ConfigError(f"Config validation failed:\n{e}") from e


def validate_config(path: str | Path | None = None) -> list[str]:
    """Validate a config file and return a list of issues (empty = valid).

    This is a softer check than load_config — it collects all errors
    rather than raising on the first one.
    """
    issues: list[str] = []
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path = config_path.expanduser().resolve()

    if not config_path.exists():
        return [f"Config file not found: {config_path}"]

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"Cannot read config file: {e}"]

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return [f"Invalid YAML: {e}"]

    if data is None:
        data = {}

    if not isinstance(data, dict):
        return ["Config file must contain a YAML mapping at the top level"]

    try:
        config = RNMConfig(**data)
    except ValidationError as e:
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            issues.append(f"{loc}: {err['msg']}")
        return issues

    # Semantic checks beyond Pydantic validation
    kiss_ports: dict[int, str] = {}
    for name, iface in config.interfaces.items():
        if not iface.enabled:
            continue
        port = iface.kiss_port
        if port in kiss_ports:
            issues.append(
                f"Interface '{name}' KISS port {port} conflicts with "
                f"interface '{kiss_ports[port]}'"
            )
        kiss_ports[port] = name

    if config.node.callsign == "N0CALL":
        issues.append("node.callsign is still the default 'N0CALL' -- set your callsign")

    return issues
