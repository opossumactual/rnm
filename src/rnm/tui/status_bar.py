"""Node info status bar for the TUI dashboard."""

from __future__ import annotations

import time

from textual.reactive import reactive
from textual.widgets import Static

from rnm.config.schema import RNMConfig


class NodeInfoBar(Static):
    """Top bar showing node name, callsign, and uptime."""

    DEFAULT_CSS = """\
NodeInfoBar {
    height: 3;
    padding: 1 2;
    background: $surface;
    color: $text;
}
"""

    uptime_text = reactive("0s")

    def __init__(self, config: RNMConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = config
        self._start_time = time.time()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._render_bar()

    def _tick(self) -> None:
        elapsed = int(time.time() - self._start_time)
        days, rem = divmod(elapsed, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(f"{secs}s")

        self.uptime_text = " ".join(parts)

    def watch_uptime_text(self) -> None:
        self._render_bar()

    def _render_bar(self) -> None:
        name = self.config.node.name
        call = self.config.node.callsign

        iface_count = sum(1 for i in self.config.interfaces.values() if i.enabled)
        iface_str = f"{iface_count} interface{'s' if iface_count != 1 else ''}"

        self.update(
            f"[bold]{name}[/bold]  ({call})    "
            f"{iface_str}    "
            f"Uptime: [cyan]{self.uptime_text}[/cyan]"
        )
