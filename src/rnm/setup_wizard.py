"""Interactive setup wizard for creating and editing RNM configs."""

from __future__ import annotations

import os
from pathlib import Path

import click
import yaml

from rnm.config.defaults import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH
from rnm.hardware.audio import AudioDevice, detect_audio_devices
from rnm.hardware.serial import SerialDevice, detect_serial_devices


def run_wizard(config_path: str | None = None) -> None:
    """Run the interactive setup wizard."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    path = path.expanduser().resolve()

    existing = _load_existing(path)

    click.echo()
    click.echo("=" * 55)
    click.echo("  Reticulum Node Manager — Setup Wizard")
    click.echo("=" * 55)
    click.echo()

    if existing:
        click.echo(f"  Existing config found: {path}")
        click.echo()
        action = _choose("What would you like to do?", [
            ("edit", "Edit existing configuration"),
            ("add", "Add a new interface"),
            ("remove", "Remove an interface"),
            ("new", "Start fresh (overwrite)"),
        ])
        if action == "edit":
            config = _edit_config(existing)
        elif action == "add":
            config = _add_interface(existing)
        elif action == "remove":
            config = _remove_interface(existing)
        else:
            config = _new_config()
    else:
        click.echo("  No existing config found. Let's create one.")
        click.echo()
        config = _new_config()

    # Write config
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.echo()
    click.echo(f"  Config written to: {path}")
    click.echo()
    click.echo("  Next steps:")
    click.echo(f"    rnm validate -c {path}")
    click.echo(f"    rnm show-config -c {path}")
    click.echo(f"    rnm start -c {path}")
    click.echo()


def _new_config() -> dict:
    """Walk through creating a brand new config."""
    config: dict = {}

    # --- Node info ---
    click.echo("-- Node Information --")
    click.echo()
    callsign = click.prompt("  Callsign", default="N0CALL")
    name = click.prompt("  Node name", default=f"{callsign}-Gateway")
    config["node"] = {"name": name, "callsign": callsign}

    # --- Interfaces ---
    config["interfaces"] = {}
    click.echo()
    click.echo("-- Interfaces --")
    click.echo("  Add radio interfaces. You can add more later with `rnm setup`.")
    click.echo()

    while True:
        if config["interfaces"]:
            click.echo(f"  Current interfaces: {', '.join(config['interfaces'].keys())}")
            if not click.confirm("  Add another interface?", default=False):
                break
            click.echo()

        iface_type = _choose("  Interface type:", [
            ("direwolf", "VHF/UHF via Direwolf (1200/9600 baud packet)"),
            ("freedvtnc2", "HF via FreeDV TNC2 (DATAC1/DATAC3/DATAC4)"),
        ])

        if iface_type == "direwolf":
            name_key, iface = _setup_direwolf(callsign)
        else:
            name_key, iface = _setup_freedvtnc2()

        config["interfaces"][name_key] = iface
        click.echo(f"  Added interface: {name_key}")
        click.echo()

        if not config["interfaces"]:
            click.echo("  You need at least one interface.")
            continue

    # --- Reticulum ---
    click.echo()
    click.echo("-- Reticulum Settings --")
    config["reticulum"] = _setup_reticulum(config["interfaces"])

    # --- Process ---
    config["process"] = {
        "restart_policy": "always",
        "restart_delay": 3,
        "max_restarts": 10,
    }

    # --- Logging ---
    config["logging"] = {"level": "info"}

    # --- TUI ---
    config["tui"] = {"enabled": True}

    return config


def _edit_config(existing: dict) -> dict:
    """Edit sections of an existing config."""
    config = dict(existing)

    section = _choose("Which section to edit?", [
        ("node", f"Node info (currently: {existing.get('node', {}).get('callsign', 'N0CALL')})"),
        ("interfaces", f"Interfaces ({len(existing.get('interfaces', {}))} configured)"),
        ("reticulum", "Reticulum settings"),
        ("process", "Process management"),
    ])

    if section == "node":
        node = config.get("node", {})
        node["callsign"] = click.prompt("  Callsign", default=node.get("callsign", "N0CALL"))
        node["name"] = click.prompt("  Node name", default=node.get("name", "Reticulum Node"))
        config["node"] = node

    elif section == "interfaces":
        interfaces = config.get("interfaces", {})
        if not interfaces:
            click.echo("  No interfaces configured. Use 'Add a new interface' instead.")
            return config

        iface_name = _choose("Which interface to edit?", [
            (k, f"{v.get('type', '?')} — KISS port {v.get('kiss_port', '?')}")
            for k, v in interfaces.items()
        ])

        iface = interfaces[iface_name]
        if iface.get("type") == "direwolf":
            interfaces[iface_name] = _edit_direwolf(iface)
        elif iface.get("type") == "freedvtnc2":
            interfaces[iface_name] = _edit_freedvtnc2(iface)
        config["interfaces"] = interfaces

    elif section == "reticulum":
        ret = config.get("reticulum", {})
        ret["enable_transport"] = click.confirm(
            "  Enable transport (route for others)?",
            default=ret.get("enable_transport", True),
        )
        ret["loglevel"] = click.prompt(
            "  Log level (0=critical, 7=verbose)",
            default=ret.get("loglevel", 4),
            type=int,
        )
        config["reticulum"] = ret

    elif section == "process":
        proc = config.get("process", {})
        proc["restart_policy"] = _choose("  Restart policy:", [
            ("always", "Always restart on exit"),
            ("on-failure", "Only restart on non-zero exit"),
            ("never", "Never auto-restart"),
        ])
        proc["restart_delay"] = click.prompt(
            "  Restart delay (seconds)",
            default=proc.get("restart_delay", 3),
            type=int,
        )
        config["process"] = proc

    return config


def _add_interface(existing: dict) -> dict:
    """Add a new interface to an existing config."""
    config = dict(existing)
    interfaces = config.get("interfaces", {})
    callsign = config.get("node", {}).get("callsign", "N0CALL")

    click.echo()
    iface_type = _choose("  Interface type:", [
        ("direwolf", "VHF/UHF via Direwolf (1200/9600 baud packet)"),
        ("freedvtnc2", "HF via FreeDV TNC2 (DATAC1/DATAC3/DATAC4)"),
    ])

    if iface_type == "direwolf":
        name_key, iface = _setup_direwolf(callsign)
    else:
        name_key, iface = _setup_freedvtnc2()

    # Avoid name collisions
    while name_key in interfaces:
        name_key = click.prompt(
            f"  Name '{name_key}' already exists. Choose a different name",
        )

    interfaces[name_key] = iface
    config["interfaces"] = interfaces
    click.echo(f"  Added interface: {name_key}")
    return config


def _remove_interface(existing: dict) -> dict:
    """Remove an interface from the config."""
    config = dict(existing)
    interfaces = config.get("interfaces", {})

    if not interfaces:
        click.echo("  No interfaces to remove.")
        return config

    name = _choose("  Which interface to remove?", [
        (k, f"{v.get('type', '?')} — KISS port {v.get('kiss_port', '?')}")
        for k, v in interfaces.items()
    ])

    if click.confirm(f"  Remove interface '{name}'?", default=False):
        del interfaces[name]
        config["interfaces"] = interfaces
        click.echo(f"  Removed: {name}")
    else:
        click.echo("  Cancelled.")

    return config


# --- Interface setup helpers ---

def _setup_direwolf(callsign: str) -> tuple[str, dict]:
    """Interactive setup for a Direwolf (VHF/UHF) interface."""
    click.echo()
    click.echo("  -- Direwolf (VHF/UHF) Setup --")
    click.echo()

    name = click.prompt("  Interface name", default="vhf_uhf")

    # Audio device
    audio_dev = _pick_audio_device("  Audio device for this radio")

    # Callsign with SSID
    iface_call = click.prompt(
        "  Callsign with SSID (e.g. W6EZE-10)",
        default=f"{callsign}-10",
    )

    # Modem
    modem = _choose("  Modem speed:", [
        ("1200", "1200 baud AFSK (standard VHF packet)"),
        ("9600", "9600 baud (dedicated data port only)"),
    ])

    # PTT
    ptt = _setup_direwolf_ptt()

    # KISS port
    kiss_port = click.prompt("  KISS TCP port", default=8001, type=int)

    iface = {
        "enabled": True,
        "type": "direwolf",
        "audio_device": audio_dev,
        "callsign": iface_call,
        "modem": int(modem),
        "ptt": ptt,
        "kiss_port": kiss_port,
        "timing": {"txdelay": 40, "txtail": 10, "slottime": 10, "persist": 63},
        "channel": 0,
    }

    return name, iface


def _setup_freedvtnc2() -> tuple[str, dict]:
    """Interactive setup for a FreeDV TNC2 (HF) interface."""
    click.echo()
    click.echo("  -- FreeDV TNC2 (HF) Setup --")
    click.echo()

    name = click.prompt("  Interface name", default="hf")

    # Audio devices
    input_dev = _pick_audio_device("  Input (RX) audio device")
    output_dev = _pick_audio_device("  Output (TX) audio device", default=input_dev)

    # Mode
    mode = _choose("  FreeDV data modem mode:", [
        ("DATAC1", "DATAC1 — ~290 bps, good HF robustness (recommended)"),
        ("DATAC3", "DATAC3 — ~126 bps, punches through rough conditions"),
        ("DATAC4", "DATAC4 — newer, experimental"),
    ])

    # PTT
    ptt_type = _choose("  PTT method:", [
        ("rigctld", "rigctld (Hamlib CAT control — recommended)"),
        ("vox", "VOX (radio's built-in voice-activated TX)"),
    ])

    ptt: dict = {"type": ptt_type}
    if ptt_type == "rigctld":
        ptt.update(_setup_rigctld())

    # KISS port
    kiss_port = click.prompt("  KISS TCP port", default=8002, type=int)

    iface = {
        "enabled": True,
        "type": "freedvtnc2",
        "input_device": input_dev,
        "output_device": output_dev,
        "mode": mode,
        "ptt": ptt,
        "kiss_port": kiss_port,
    }

    return name, iface


def _setup_direwolf_ptt() -> dict:
    """Interactive PTT setup for Direwolf."""
    ptt_type = _choose("  PTT control method:", [
        ("serial", "Serial port (RTS/DTR)"),
        ("gpio", "GPIO pin (Raspberry Pi)"),
        ("cm108", "CM108 USB sound card PTT"),
        ("none", "None (no PTT, receive only)"),
    ])

    ptt: dict = {"type": ptt_type}

    if ptt_type == "serial":
        ptt["device"] = _pick_serial_device("  PTT serial device")
        ptt["line"] = _choose("  PTT line:", [
            ("RTS", "RTS (most common)"),
            ("DTR", "DTR"),
        ])
    elif ptt_type == "gpio":
        ptt["gpio_pin"] = click.prompt("  GPIO pin number", type=int)

    return ptt


def _setup_rigctld() -> dict:
    """Interactive rigctld setup for FreeDV TNC2."""
    click.echo()
    click.echo("  -- rigctld (Hamlib) Configuration --")

    rig_model = click.prompt(
        "  Hamlib rig model number (use `rigctl -l` to find yours, 1=dummy for testing)",
        default=1,
        type=int,
    )

    result: dict = {
        "rigctld_host": "127.0.0.1",
        "rigctld_port": 4532,
        "rig_model": rig_model,
    }

    if rig_model != 1:
        result["rig_device"] = _pick_serial_device("  CAT serial device")
        result["rig_speed"] = click.prompt("  CAT serial baud rate", default=9600, type=int)

    return result


def _edit_direwolf(iface: dict) -> dict:
    """Edit an existing Direwolf interface config."""
    click.echo()
    click.echo("  -- Edit Direwolf Interface --")
    click.echo("  (Press Enter to keep current value)")
    click.echo()

    iface["audio_device"] = _pick_audio_device(
        "  Audio device", default=iface.get("audio_device", "")
    )
    iface["callsign"] = click.prompt("  Callsign", default=iface.get("callsign", ""))

    modem = _choose("  Modem speed:", [
        ("1200", "1200 baud AFSK"),
        ("9600", "9600 baud"),
    ])
    iface["modem"] = int(modem)

    iface["kiss_port"] = click.prompt(
        "  KISS TCP port", default=iface.get("kiss_port", 8001), type=int,
    )

    if click.confirm("  Reconfigure PTT?", default=False):
        iface["ptt"] = _setup_direwolf_ptt()

    return iface


def _edit_freedvtnc2(iface: dict) -> dict:
    """Edit an existing FreeDV TNC2 interface config."""
    click.echo()
    click.echo("  -- Edit FreeDV TNC2 Interface --")
    click.echo("  (Press Enter to keep current value)")
    click.echo()

    iface["input_device"] = _pick_audio_device(
        "  Input device", default=iface.get("input_device", "")
    )
    iface["output_device"] = _pick_audio_device(
        "  Output device", default=iface.get("output_device", "")
    )

    mode = _choose("  FreeDV mode:", [
        ("DATAC1", "DATAC1 — ~290 bps"),
        ("DATAC3", "DATAC3 — ~126 bps"),
        ("DATAC4", "DATAC4 — experimental"),
    ])
    iface["mode"] = mode

    iface["kiss_port"] = click.prompt(
        "  KISS TCP port", default=iface.get("kiss_port", 8002), type=int,
    )

    if click.confirm("  Reconfigure PTT?", default=False):
        ptt_type = iface.get("ptt", {}).get("type", "rigctld")
        ptt_choice = _choose("  PTT method:", [
            ("rigctld", "rigctld (Hamlib)"),
            ("vox", "VOX"),
        ])
        ptt: dict = {"type": ptt_choice}
        if ptt_choice == "rigctld":
            ptt.update(_setup_rigctld())
        iface["ptt"] = ptt

    return iface


def _setup_reticulum(interfaces: dict) -> dict:
    """Configure Reticulum settings."""
    ret: dict = {}
    ret["enable_transport"] = click.confirm(
        "  Enable transport (route packets for other nodes)?", default=True,
    )
    ret["share_instance"] = click.confirm(
        "  Share instance (let local apps like NomadNet use this Reticulum)?",
        default=True,
    )
    ret["loglevel"] = click.prompt(
        "  Log level (0=critical, 4=info, 7=verbose)", default=4, type=int,
    )

    # TCP server for remote Reticulum connections
    if click.confirm("  Enable TCP server (so other nodes can connect to you)?", default=True):
        port = click.prompt("  TCP server listen port", default=4242, type=int)
        ret["additional_interfaces"] = {
            "tcp_server": {
                "type": "TCPServerInterface",
                "enabled": True,
                "listen_ip": "0.0.0.0",
                "listen_port": port,
            }
        }

    return ret


# --- UI helpers ---

def _choose(prompt: str, options: list[tuple[str, str]]) -> str:
    """Present a numbered choice menu and return the selected key."""
    click.echo(prompt)
    for i, (key, desc) in enumerate(options, 1):
        click.echo(f"    {i}) {desc}")

    while True:
        choice = click.prompt("  Choice", type=int, default=1)
        if 1 <= choice <= len(options):
            return options[choice - 1][0]
        click.echo(f"  Please enter 1-{len(options)}")


def _pick_audio_device(prompt: str, default: str = "") -> str:
    """Let the user pick from detected audio devices or type manually."""
    devices = detect_audio_devices()

    if devices:
        click.echo(f"{prompt}:")
        click.echo("    Detected devices:")
        for i, dev in enumerate(devices, 1):
            usb_tag = " [USB]" if dev.is_usb else ""
            click.echo(f"      {i}) {dev.alsa_name} — {dev.name}{usb_tag}")
        click.echo(f"      {len(devices) + 1}) Enter manually")

        choice = click.prompt(
            "    Choice",
            type=int,
            default=1 if not default else None,
        )
        if 1 <= choice <= len(devices):
            return devices[choice - 1].alsa_name

    # Manual entry
    return click.prompt(f"{prompt} (ALSA name, e.g. plughw:1,0)", default=default or "plughw:1,0")


def _pick_serial_device(prompt: str, default: str = "") -> str:
    """Let the user pick from detected serial devices or type manually."""
    devices = detect_serial_devices()

    if devices:
        click.echo(f"{prompt}:")
        click.echo("    Detected devices:")
        for i, dev in enumerate(devices, 1):
            path_str = dev.by_id or dev.path
            click.echo(f"      {i}) {path_str} — {dev.name}")
        click.echo(f"      {len(devices) + 1}) Enter manually")

        choice = click.prompt(
            "    Choice",
            type=int,
            default=1 if not default else None,
        )
        if 1 <= choice <= len(devices):
            # Prefer by-id path for persistence
            return devices[choice - 1].by_id or devices[choice - 1].path

    # Manual entry
    return click.prompt(f"{prompt} (device path)", default=default or "/dev/ttyUSB0")


def _load_existing(path: Path) -> dict | None:
    """Load existing config file as raw dict, or None."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
