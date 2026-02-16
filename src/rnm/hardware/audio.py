"""Detect and enumerate audio devices for Direwolf and FreeDV TNC2."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class AudioDevice:
    card_num: int
    device_num: int
    name: str
    alsa_name: str  # e.g. "plughw:1,0"
    is_usb: bool = False


def detect_audio_devices() -> list[AudioDevice]:
    """Detect audio devices by parsing aplay -l output.

    Returns a list of AudioDevice with ALSA names suitable for
    Direwolf (plughw:N,N format) and descriptions.
    """
    devices: list[AudioDevice] = []

    for cmd in (["aplay", "-l"], ["arecord", "-l"]):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                continue
            for dev in _parse_aplay_output(result.stdout):
                # Deduplicate by alsa_name
                if not any(d.alsa_name == dev.alsa_name for d in devices):
                    devices.append(dev)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return devices


def _parse_aplay_output(output: str) -> list[AudioDevice]:
    """Parse output of `aplay -l` or `arecord -l`."""
    devices = []
    # Lines look like: "card 1: Device [USB Audio CODEC], device 0: USB Audio [USB Audio]"
    pattern = re.compile(
        r"^card\s+(\d+):\s+(\S+)\s+\[(.+?)\],\s+device\s+(\d+):"
    )
    for line in output.splitlines():
        m = pattern.match(line)
        if m:
            card = int(m.group(1))
            device = int(m.group(4))
            name = m.group(3)
            alsa_name = f"plughw:{card},{device}"
            is_usb = "usb" in line.lower()
            devices.append(AudioDevice(
                card_num=card,
                device_num=device,
                name=name,
                alsa_name=alsa_name,
                is_usb=is_usb,
            ))
    return devices
