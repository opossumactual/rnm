"""Async process supervisor for all managed services."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

from rnm.config.schema import RNMConfig
from rnm.process.services import ServiceDefinition, build_services

logger = logging.getLogger("rnm.supervisor")


@dataclass
class ProcessState:
    service: ServiceDefinition
    process: Optional[asyncio.subprocess.Process] = None
    state: str = "stopped"  # stopped | starting | running | failed | stopping
    restart_count: int = 0
    last_restart: float = 0
    last_health_check: float = 0
    start_time: Optional[float] = None


class Supervisor:
    """Async process supervisor for all managed services."""

    def __init__(self, config: RNMConfig, generated_dir: str):
        self.config = config
        self.generated_dir = generated_dir
        self.processes: Dict[str, ProcessState] = {}
        self.running = False
        self._event_callbacks: list[Callable] = []
        self._health_task: asyncio.Task | None = None

    def on_event(self, callback: Callable) -> None:
        """Register callback for process events (for TUI updates)."""
        self._event_callbacks.append(callback)

    def _emit(self, event: str, name: str, detail: object = None) -> None:
        for cb in self._event_callbacks:
            try:
                cb(event, name, detail)
            except Exception:
                pass
        logger.info("Event: %s service=%s detail=%s", event, name, detail)

    async def start_all(self) -> None:
        """Start all services and block until stopped (for TUI mode)."""
        await self.start_services()
        await self._wait_for_exit()

    async def start_services(self) -> None:
        """Start all services in dependency order (non-blocking)."""
        self.running = True
        services = build_services(self.config, self.generated_dir)

        # Write generated config files
        self._write_configs(services)

        # Topological sort by depends_on
        ordered = self._dependency_sort(services)

        for svc in ordered:
            self.processes[svc.name] = ProcessState(service=svc)
            await self._start_service(svc.name)
            # Brief pause to let the service bind its port
            await asyncio.sleep(1)

        # Start health check loop in background
        self._health_task = asyncio.create_task(self._health_check_loop())

    def _write_configs(self, services: list[ServiceDefinition]) -> None:
        """Write generated config files to disk."""
        from rnm.generators.reticulum import generate_reticulum_config

        gen_dir = Path(self.generated_dir)
        gen_dir.mkdir(parents=True, exist_ok=True)

        # Write direwolf configs
        for svc in services:
            for conf_path in svc.config_files:
                # Find the matching interface to regenerate
                for iface_name, iface in self.config.interfaces.items():
                    if svc.name == f"direwolf_{iface_name}":
                        from rnm.generators.direwolf import generate_direwolf_conf

                        content = generate_direwolf_conf(iface_name, iface)
                        p = Path(conf_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(content, encoding="utf-8")
                        logger.info("Wrote %s", conf_path)

        # Write reticulum config
        ret_dir = gen_dir / "reticulum"
        ret_dir.mkdir(parents=True, exist_ok=True)
        ret_config = generate_reticulum_config(self.config)
        (ret_dir / "config").write_text(ret_config, encoding="utf-8")
        logger.info("Wrote %s", ret_dir / "config")

        # Copy transport_identity from user's default Reticulum config so
        # rnsd shares the same RPC auth key and network identity.
        import shutil

        user_identity = Path.home() / ".reticulum" / "storage" / "transport_identity"
        dest_identity = ret_dir / "storage" / "transport_identity"
        if user_identity.exists():
            dest_identity.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(user_identity, dest_identity)
            logger.info("Copied transport_identity from %s", user_identity)

    def _dependency_sort(self, services: list[ServiceDefinition]) -> list[ServiceDefinition]:
        """Topological sort of services by depends_on."""
        by_name = {s.name: s for s in services}
        visited: set[str] = set()
        result: list[ServiceDefinition] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            svc = by_name.get(name)
            if svc is None:
                return
            for dep in svc.depends_on:
                visit(dep)
            result.append(svc)

        for s in services:
            visit(s.name)

        return result

    async def _start_service(self, name: str) -> None:
        """Start a single service."""
        ps = self.processes[name]
        ps.state = "starting"
        self._emit("state_change", name, "starting")

        try:
            proc_env = {
                **os.environ,
                "PATH": f"{Path.home()}/.local/bin:{os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')}",
                "LD_LIBRARY_PATH": f"/usr/local/lib:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":"),
            }
            proc_env.update(ps.service.env)

            ps.process = await asyncio.create_subprocess_exec(
                *ps.service.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ps.service.working_dir,
                env=proc_env,
            )
            ps.state = "running"
            ps.start_time = time.time()
            self._emit("state_change", name, "running")

            asyncio.create_task(self._watch_process(name))
            asyncio.create_task(self._read_output(name, ps.process.stdout, "stdout"))
            asyncio.create_task(self._read_output(name, ps.process.stderr, "stderr"))

        except Exception as e:
            ps.state = "failed"
            self._emit("error", name, str(e))
            logger.error("Failed to start %s: %s", name, e)

    async def _watch_process(self, name: str) -> None:
        """Watch a process and handle unexpected exits."""
        ps = self.processes[name]
        returncode = await ps.process.wait()

        if not self.running:
            return

        ps.state = "failed"
        self._emit("exit", name, returncode)
        logger.warning("%s exited with code %d", name, returncode)

        # Handle restart policy
        if self.config.process.restart_policy == "never":
            return
        if self.config.process.restart_policy == "on-failure" and returncode == 0:
            return

        now = time.time()
        if now - ps.last_restart > self.config.process.restart_window:
            ps.restart_count = 0

        max_r = self.config.process.max_restarts
        if max_r > 0 and ps.restart_count >= max_r:
            self._emit("max_restarts", name)
            logger.error("%s hit max restarts (%d), giving up", name, max_r)
            return

        ps.restart_count += 1
        ps.last_restart = now
        logger.info("Restarting %s (attempt %d)", name, ps.restart_count)

        await asyncio.sleep(self.config.process.restart_delay)
        if self.running:
            await self._start_service(name)

    async def _read_output(self, name: str, stream, label: str) -> None:
        """Read process output and log it."""
        proc_logger = logging.getLogger(f"rnm.{name}")
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                proc_logger.info("[%s] %s", label, text)
                self._emit("output", name, text)

    async def _health_check_loop(self) -> None:
        """Periodically check service health via TCP probes."""
        await asyncio.sleep(self.config.process.startup_grace_period)

        while self.running:
            for name, ps in self.processes.items():
                if ps.state == "running" and ps.service.health_check:
                    try:
                        healthy = await ps.service.health_check()
                        if not healthy:
                            self._emit("unhealthy", name)
                            logger.warning("%s health check failed", name)
                    except Exception:
                        self._emit("health_error", name)
            await asyncio.sleep(self.config.process.health_check_interval)

    async def _wait_for_exit(self) -> None:
        """Wait until self.running is set to False."""
        while self.running:
            await asyncio.sleep(1)

    async def stop_all(self) -> None:
        """Gracefully stop all services in reverse order."""
        self.running = False
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
        for name in reversed(list(self.processes.keys())):
            await self._stop_service(name)

    async def _stop_service(self, name: str) -> None:
        """Stop a single service gracefully."""
        ps = self.processes[name]
        if ps.process and ps.process.returncode is None:
            ps.state = "stopping"
            self._emit("state_change", name, "stopping")
            ps.process.terminate()
            try:
                await asyncio.wait_for(ps.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                ps.process.kill()
                await ps.process.wait()
            ps.state = "stopped"
            self._emit("state_change", name, "stopped")
            logger.info("Stopped %s", name)

    def get_status(self) -> dict[str, dict]:
        """Return current status of all processes."""
        result = {}
        for name, ps in self.processes.items():
            uptime = None
            if ps.start_time and ps.state == "running":
                uptime = time.time() - ps.start_time
            result[name] = {
                "state": ps.state,
                "pid": ps.process.pid if ps.process else None,
                "restarts": ps.restart_count,
                "uptime": uptime,
                "command": " ".join(ps.service.command),
            }
        return result
