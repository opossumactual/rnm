"""Click CLI for Reticulum Node Manager."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import click

from rnm import __version__
from rnm.config.defaults import DEFAULT_CONFIG_PATH, GENERATED_CONFIG_DIR


@click.group()
@click.option(
    "--config", "-c",
    default=str(DEFAULT_CONFIG_PATH),
    envvar="RNM_CONFIG",
    help="Config file path",
    type=click.Path(),
)
@click.version_option(__version__, prog_name="rnm")
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """Reticulum Node Manager -- Unified radio mesh node management."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = os.path.expanduser(config)


# ---------- start ----------

@cli.command()
@click.option("--headless", is_flag=True, help="Run without TUI (for systemd)")
@click.pass_context
def start(ctx: click.Context, headless: bool) -> None:
    """Start all configured services."""
    from rnm.config.loader import ConfigError, load_config
    from rnm.process.manager import read_pid, run_headless

    existing = read_pid()
    if existing:
        click.echo(f"Error: rnm is already running (PID {existing})", err=True)
        raise SystemExit(1)

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if headless or not config.tui.enabled:
        asyncio.run(run_headless(config))
    else:
        from rnm.tui.app import RNMApp
        app = RNMApp(config)
        app.run()


# ---------- stop ----------

@cli.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop all managed services."""
    from rnm.process.manager import read_pid, remove_pid_file

    pid = read_pid()
    if pid is None:
        click.echo("rnm is not running.")
        return

    click.echo(f"Sending SIGTERM to rnm (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo("Stop signal sent.")
    except ProcessLookupError:
        click.echo("Process not found — cleaning up stale PID file.")
        remove_pid_file()
    except PermissionError:
        click.echo("Permission denied. Try with sudo.", err=True)
        raise SystemExit(1)


# ---------- status ----------

@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current status of all services."""
    from rnm.process.manager import read_pid

    pid = read_pid()
    if pid is None:
        click.echo("rnm is not running.")
        return

    click.echo(f"rnm is running (PID {pid})")
    # TODO: connect to running instance for detailed status


# ---------- check ----------

@cli.command()
@click.option("--all", "include_optional", is_flag=True, help="Include optional dependencies")
@click.pass_context
def check(ctx: click.Context, include_optional: bool) -> None:
    """Check that all dependencies are installed."""
    from rnm.utils.deps import check_dependencies

    deps = check_dependencies(include_optional)
    has_missing = False

    click.echo("Dependency Check")
    click.echo("=" * 50)

    for dep in deps:
        if dep.found:
            marker = click.style("  OK ", fg="green")
            info = dep.path or ""
            click.echo(f"{marker}  {dep.description} ({dep.command})")
            if info:
                click.echo(f"        {info}")
        else:
            if dep.required:
                marker = click.style(" MISS", fg="red")
                has_missing = True
            else:
                marker = click.style(" SKIP", fg="yellow")
            click.echo(f"{marker}  {dep.description} ({dep.command})")

    click.echo()
    if has_missing:
        click.echo("Some required dependencies are missing.")
        click.echo("Run the install script: scripts/install-deps.sh")
        raise SystemExit(1)
    else:
        click.echo("All required dependencies are installed.")


# ---------- validate ----------

@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate configuration file."""
    from rnm.config.loader import validate_config

    config_path = ctx.obj["config_path"]
    click.echo(f"Validating: {config_path}")
    click.echo()

    issues = validate_config(config_path)

    if not issues:
        click.echo(click.style("Configuration is valid.", fg="green"))
    else:
        for issue in issues:
            severity = "warning" if "default" in issue.lower() else "error"
            color = "yellow" if severity == "warning" else "red"
            click.echo(click.style(f"  [{severity}] {issue}", fg=color))
        click.echo()
        # Warnings (like default callsign) don't cause exit(1)
        errors = [i for i in issues if "default" not in i.lower()]
        if errors:
            raise SystemExit(1)


# ---------- show-config ----------

@cli.command("show-config")
@click.option(
    "--format", "fmt",
    type=click.Choice(["yaml", "direwolf", "freedvtnc2", "rigctld", "reticulum", "all"]),
    default="all",
    help="Which generated config to show",
)
@click.pass_context
def show_config(ctx: click.Context, fmt: str) -> None:
    """Show generated config files."""
    from rnm.config.loader import ConfigError, load_config
    from rnm.config.schema import DirewolfInterface, FreeDVInterface
    from rnm.generators.direwolf import generate_direwolf_conf
    from rnm.generators.freedvtnc2 import build_freedvtnc2_args, build_rigctld_args
    from rnm.generators.reticulum import generate_reticulum_config

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    sections_shown = 0

    for iface_name, iface in config.interfaces.items():
        if not iface.enabled:
            continue

        if isinstance(iface, DirewolfInterface) and fmt in ("direwolf", "all"):
            click.echo(f"--- direwolf.conf ({iface_name}) ---")
            click.echo(generate_direwolf_conf(iface_name, iface))
            sections_shown += 1

        if isinstance(iface, FreeDVInterface):
            if fmt in ("freedvtnc2", "all"):
                args = build_freedvtnc2_args(iface)
                click.echo(f"--- freedvtnc2 args ({iface_name}) ---")
                click.echo(" ".join(args))
                click.echo()
                sections_shown += 1

            if fmt in ("rigctld", "all") and iface.ptt.type == "rigctld":
                args = build_rigctld_args(iface.ptt)
                click.echo(f"--- rigctld args ({iface_name}) ---")
                click.echo(" ".join(args))
                click.echo()
                sections_shown += 1

    if fmt in ("reticulum", "all"):
        click.echo("--- reticulum config ---")
        click.echo(generate_reticulum_config(config))
        sections_shown += 1

    if sections_shown == 0:
        click.echo("No enabled interfaces found in config.")


# ---------- setup ----------

@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Interactive setup wizard — create or edit configuration."""
    from rnm.setup_wizard import run_wizard
    run_wizard(ctx.obj["config_path"])


# ---------- devices ----------

@cli.group()
def devices() -> None:
    """Hardware device utilities."""
    pass


@devices.command("audio")
def list_audio() -> None:
    """List available audio devices."""
    from rnm.hardware.audio import detect_audio_devices

    devs = detect_audio_devices()
    if devs:
        click.echo("=== Audio Devices ===")
        for dev in devs:
            usb_tag = " [USB]" if dev.is_usb else ""
            click.echo(f"  {dev.alsa_name}  {dev.name}{usb_tag}")
    else:
        click.echo("No audio devices detected (is aplay/arecord installed?)")


@devices.command("serial")
def list_serial() -> None:
    """List available serial devices for PTT/CAT control."""
    from rnm.hardware.serial import detect_serial_devices

    devs = detect_serial_devices()
    if devs:
        click.echo("=== Serial Devices ===")
        for dev in devs:
            path = dev.by_id or dev.path
            click.echo(f"  {path}")
            if dev.by_id:
                click.echo(f"    -> {dev.path}  ({dev.name})")
    else:
        click.echo("No serial devices detected.")


@devices.command("rigs")
def list_rigs() -> None:
    """List Hamlib-supported rig models."""
    import subprocess

    try:
        result = subprocess.run(
            ["rigctl", "-l"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo("rigctl failed. Is Hamlib installed?", err=True)
    except FileNotFoundError:
        click.echo("rigctl not found. Install with: sudo apt install libhamlib-utils", err=True)
    except subprocess.TimeoutExpired:
        click.echo("rigctl timed out.", err=True)


# ---------- install-service ----------

@cli.command("install-service")
@click.pass_context
def install_service(ctx: click.Context) -> None:
    """Install rnm as a systemd service for auto-start on boot."""
    import getpass
    import shutil

    rnm_path = shutil.which("rnm")
    if not rnm_path:
        click.echo("Error: cannot find 'rnm' in PATH. Is it installed?", err=True)
        raise SystemExit(1)

    config_path = os.path.abspath(ctx.obj["config_path"])
    user = getpass.getuser()
    home = str(Path.home())

    unit = f"""\
[Unit]
Description=Reticulum Node Manager
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User={user}
Environment="PATH={home}/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="LD_LIBRARY_PATH=/usr/local/lib"
ExecStart={rnm_path} start --headless -c {config_path}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    click.echo("Generated systemd unit:")
    click.echo(unit)
    click.echo(f"This will be written to /etc/systemd/system/rnm.service")

    if not click.confirm("Install and enable?"):
        return

    unit_path = "/etc/systemd/system/rnm.service"
    try:
        import subprocess

        # Write unit file via sudo tee
        proc = subprocess.run(
            ["sudo", "tee", unit_path],
            input=unit, text=True, capture_output=True,
        )
        if proc.returncode != 0:
            click.echo(f"Failed to write unit file: {proc.stderr}", err=True)
            raise SystemExit(1)

        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        subprocess.run(["sudo", "systemctl", "enable", "rnm"], check=True)
        click.echo("Service installed and enabled.")

        if click.confirm("Start service now?"):
            subprocess.run(["sudo", "systemctl", "start", "rnm"], check=True)
            click.echo("Service started.")

    except subprocess.CalledProcessError as e:
        click.echo(f"systemctl error: {e}", err=True)
        raise SystemExit(1)
