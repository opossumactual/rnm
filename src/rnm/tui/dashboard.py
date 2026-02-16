"""Service status panel for the TUI dashboard."""

from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.containers import Vertical


class ServicePanel(Vertical):
    """Panel showing the status of all managed services."""

    DEFAULT_CSS = """\
ServicePanel {
    height: auto;
    padding: 0 1;
}

ServicePanel DataTable {
    height: auto;
    max-height: 12;
}

ServicePanel #svc-title {
    text-style: bold;
    padding: 0 0 0 0;
    height: 1;
}
"""

    def compose(self):
        yield Static("Services", id="svc-title")
        yield DataTable(id="svc-table")

    def on_mount(self) -> None:
        table = self.query_one("#svc-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_columns("Service", "Status", "Details")

    def update_service(self, name: str, state: str) -> None:
        """Update or add a service row in the table."""
        table = self.query_one("#svc-table", DataTable)

        # Status indicator
        indicators = {
            "starting": "[yellow]~[/yellow] Starting",
            "running": "[green]●[/green] Running",
            "stopping": "[yellow]~[/yellow] Stopping",
            "stopped": "[dim]○[/dim] Stopped",
            "failed": "[red]✗[/red] Failed",
        }
        status_text = indicators.get(state, state)

        # Build details string from supervisor state if available
        details = ""
        app = self.app
        if hasattr(app, "supervisor") and app.supervisor:
            ps = app.supervisor.processes.get(name)
            if ps:
                parts = []
                if ps.process and ps.process.pid:
                    parts.append(f"PID {ps.process.pid}")
                if ps.restart_count > 0:
                    parts.append(f"restarts: {ps.restart_count}")
                # Show KISS port if it's a TNC service
                cmd_str = " ".join(ps.service.command)
                if "--kiss-tcp-port" in cmd_str or "KISSPORT" in cmd_str:
                    for iface_name, iface in app.config.interfaces.items():
                        if name.endswith(iface_name):
                            parts.append(f"KISS:{iface.kiss_port}")
                            break
                details = "  ".join(parts)

        # Check if row exists already — update it, otherwise add
        display_name = _format_service_name(name)
        try:
            row_key = name
            table.update_cell(row_key, "Status", status_text)
            table.update_cell(row_key, "Details", details)
        except Exception:
            # Row doesn't exist yet, add it
            table.add_row(display_name, status_text, details, key=name)


def _format_service_name(name: str) -> str:
    """Make service names more readable."""
    if name.startswith("direwolf_"):
        iface = name[len("direwolf_"):]
        return f"Direwolf ({iface})"
    elif name.startswith("freedvtnc2_"):
        iface = name[len("freedvtnc2_"):]
        return f"FreeDV TNC2 ({iface})"
    elif name == "rigctld":
        return "rigctld"
    elif name == "rnsd":
        return "rnsd (Reticulum)"
    return name
