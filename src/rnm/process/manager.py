"""High-level process management: generate configs, write PID file, run supervisor."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from rnm.config.defaults import GENERATED_CONFIG_DIR, PID_FILE
from rnm.config.schema import RNMConfig
from rnm.process.supervisor import Supervisor
from rnm.utils.logging import setup_logging

logger = logging.getLogger("rnm.manager")


def write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def read_pid() -> int | None:
    """Read PID from the PID file, or None if not running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process is actually running
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        return None


async def run_headless(config: RNMConfig) -> None:
    """Run the supervisor in headless mode (no TUI)."""
    setup_logging(config.logging)
    logger.info("Starting Reticulum Node Manager (headless)")
    logger.info("Node: %s (%s)", config.node.name, config.node.callsign)

    gen_dir = str(GENERATED_CONFIG_DIR)
    supervisor = Supervisor(config, gen_dir)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_event_loop()

    def handle_signal() -> None:
        if shutdown_event.is_set():
            return  # Already shutting down
        logger.info("Received shutdown signal, stopping services...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    write_pid_file()
    try:
        # Start services (non-blocking — returns after launching)
        await supervisor.start_services()

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Graceful shutdown
        await supervisor.stop_all()
    finally:
        remove_pid_file()
        logger.info("Reticulum Node Manager stopped")
