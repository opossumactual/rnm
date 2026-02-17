"""Main Textual application for Reticulum Node Manager."""

from __future__ import annotations

import asyncio
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header

from rnm.config.defaults import GENERATED_CONFIG_DIR
from rnm.config.schema import RNMConfig
from rnm.process.supervisor import Supervisor
from rnm.tui.dashboard import ServicePanel
from rnm.tui.log_viewer import LogPanel
from rnm.tui.status_bar import NodeInfoBar


class SupervisorEvent(Message):
    """Message posted from supervisor worker to main thread."""

    def __init__(self, event: str, name: str, detail: object = None) -> None:
        super().__init__()
        self.event = event
        self.name = name
        self.detail = detail


class RNMApp(App):
    """Reticulum Node Manager TUI Dashboard."""

    TITLE = "Reticulum Node Manager"

    CSS = """\
Screen {
    layout: vertical;
}

#node-info {
    height: 3;
    background: $surface;
    color: $text;
    padding: 0 2;
    content-align: left middle;
}

#services-panel {
    height: auto;
    max-height: 50%;
    border-top: solid $primary;
    border-bottom: solid $primary;
    padding: 0 1;
}

#log-panel {
    height: 1fr;
    min-height: 8;
}
"""

    BINDINGS = [
        Binding("s", "start_all", "Start All"),
        Binding("t", "stop_all", "Stop All"),
        Binding("r", "restart_all", "Restart All"),
        Binding("c", "show_config", "Config"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, config: RNMConfig) -> None:
        super().__init__()
        self.config = config
        self.gen_dir = str(GENERATED_CONFIG_DIR)
        self.supervisor: Supervisor | None = None
        self._start_time = time.time()

    def compose(self) -> ComposeResult:
        yield Header()
        yield NodeInfoBar(self.config, id="node-info")
        yield ServicePanel(id="services-panel")
        yield LogPanel(
            max_lines=self.config.tui.log_lines,
            id="log-panel",
        )
        yield Footer()

    async def on_mount(self) -> None:
        self.supervisor = Supervisor(self.config, self.gen_dir)
        self.supervisor.on_event(self._handle_event)

        log = self.query_one("#log-panel", LogPanel)
        log.write_line("[bold]Reticulum Node Manager v0.1.0[/bold]")
        log.write_line(f"Node: {self.config.node.name} ({self.config.node.callsign})")
        log.write_line("")

        self.run_worker(self._run_supervisor, exclusive=True)

    async def _run_supervisor(self) -> None:
        """Start the supervisor in a background worker."""
        log = self.query_one("#log-panel", LogPanel)
        log.write_line("[dim]Starting services...[/dim]")
        try:
            await self.supervisor.start_services()
        except Exception as e:
            log.write_line(f"[bold red]Supervisor error: {e}[/bold red]")

    def _handle_event(self, event: str, name: str, detail: object = None) -> None:
        """Forward supervisor events to the main thread via Textual messages."""
        self.post_message(SupervisorEvent(event, name, detail))

    def on_supervisor_event(self, message: SupervisorEvent) -> None:
        """Process supervisor events on the main thread."""
        event = message.event
        name = message.name
        detail = message.detail

        try:
            svc_panel = self.query_one("#services-panel", ServicePanel)
            log = self.query_one("#log-panel", LogPanel)
        except Exception:
            return

        if event == "state_change":
            svc_panel.update_service(name, str(detail))
            state_colors = {
                "starting": "yellow",
                "running": "green",
                "stopping": "yellow",
                "stopped": "dim",
                "failed": "red",
            }
            color = state_colors.get(str(detail), "white")
            log.write_line(f"[{color}][{name}] {detail}[/{color}]")

        elif event == "exit":
            svc_panel.update_service(name, "failed")
            log.write_line(f"[red][{name}] exited with code {detail}[/red]")

        elif event == "error":
            svc_panel.update_service(name, "failed")
            log.write_line(f"[bold red][{name}] error: {detail}[/bold red]")

        elif event == "output":
            log.write_line(f"[dim][{name}][/dim] {detail}")

        elif event == "unhealthy":
            log.write_line(f"[yellow][{name}] health check failed[/yellow]")

        elif event == "max_restarts":
            log.write_line(f"[bold red][{name}] max restarts reached, giving up[/bold red]")

    # --- Actions ---

    async def action_start_all(self) -> None:
        if self.supervisor and not self.supervisor.running:
            log = self.query_one("#log-panel", LogPanel)
            log.write_line("[dim]Starting all services...[/dim]")
            self.run_worker(self._run_supervisor, exclusive=True)

    async def action_stop_all(self) -> None:
        if self.supervisor and self.supervisor.running:
            log = self.query_one("#log-panel", LogPanel)
            log.write_line("[dim]Stopping all services...[/dim]")
            await self.supervisor.stop_all()

    async def action_restart_all(self) -> None:
        if self.supervisor:
            log = self.query_one("#log-panel", LogPanel)
            log.write_line("[dim]Restarting all services...[/dim]")
            if self.supervisor.running:
                await self.supervisor.stop_all()
            await asyncio.sleep(1)
            self.run_worker(self._run_supervisor, exclusive=True)

    def action_show_config(self) -> None:
        log = self.query_one("#log-panel", LogPanel)
        log.write_line("")
        log.write_line("[bold]--- Current Configuration ---[/bold]")
        log.write_line(f"  Node: {self.config.node.name}")
        log.write_line(f"  Callsign: {self.config.node.callsign}")
        for iface_name, iface in self.config.interfaces.items():
            status = "enabled" if iface.enabled else "disabled"
            if hasattr(iface, "kiss_port"):
                detail = f"KISS:{iface.kiss_port}"
            else:
                detail = f"device:{iface.device}"
            log.write_line(f"  Interface {iface_name}: {iface.type} ({status}) {detail}")
        log.write_line("")

    async def action_quit_app(self) -> None:
        if self.supervisor and self.supervisor.running:
            log = self.query_one("#log-panel", LogPanel)
            log.write_line("[dim]Shutting down...[/dim]")
            await self.supervisor.stop_all()
        self.exit()
