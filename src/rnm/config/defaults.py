"""Sensible defaults and paths for RNM configuration."""

from pathlib import Path

# Default config file location
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "rnm"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"
GENERATED_CONFIG_DIR = DEFAULT_CONFIG_DIR / "generated"
PID_FILE = DEFAULT_CONFIG_DIR / "rnm.pid"

# Reticulum managed config directory (separate from user's ~/.reticulum)
RETICULUM_CONFIG_DIR = GENERATED_CONFIG_DIR / "reticulum"

# Default KISS TCP ports
DEFAULT_DIREWOLF_KISS_PORT = 8001
DEFAULT_FREEDVTNC2_KISS_PORT = 8002

# Default rigctld port
DEFAULT_RIGCTLD_PORT = 4532
