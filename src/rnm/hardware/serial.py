"""Detect and enumerate serial devices for PTT/CAT control."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SerialDevice:
    path: str           # e.g. "/dev/ttyUSB0"
    by_id: str | None   # e.g. "/dev/serial/by-id/usb-Silicon_Labs_..."
    name: str           # Human-readable name from by-id or device name


def detect_serial_devices() -> list[SerialDevice]:
    """Detect serial devices available for PTT/CAT control.

    Prefers /dev/serial/by-id/ paths since they're persistent
    across reboots. Falls back to /dev/ttyUSB* and /dev/ttyACM*.
    """
    devices: list[SerialDevice] = []
    seen_targets: set[str] = set()

    # First: by-id paths (persistent, preferred)
    by_id_dir = Path("/dev/serial/by-id")
    if by_id_dir.exists():
        for entry in sorted(by_id_dir.iterdir()):
            target = str(entry.resolve())
            if target not in seen_targets:
                seen_targets.add(target)
                # Extract a readable name from the by-id symlink name
                name = entry.name.replace("usb-", "").rsplit("-if", 1)[0]
                devices.append(SerialDevice(
                    path=target,
                    by_id=str(entry),
                    name=name,
                ))

    # Second: direct device nodes not already found via by-id
    dev = Path("/dev")
    for pattern in ("ttyUSB*", "ttyACM*"):
        for p in sorted(dev.glob(pattern)):
            path = str(p)
            if path not in seen_targets:
                seen_targets.add(path)
                devices.append(SerialDevice(
                    path=path,
                    by_id=None,
                    name=p.name,
                ))

    return devices
