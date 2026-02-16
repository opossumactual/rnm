"""Live log viewer widget for the TUI dashboard."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import RichLog, Static


class LogPanel(Vertical):
    """Panel showing live log output from all managed services."""

    DEFAULT_CSS = """\
LogPanel {
    height: 1fr;
    padding: 0 1;
}

LogPanel #log-title {
    text-style: bold;
    height: 1;
}

LogPanel RichLog {
    height: 1fr;
    border: solid $surface-lighten-2;
    scrollbar-size: 1 1;
}
"""

    def __init__(self, max_lines: int = 50, **kwargs) -> None:
        super().__init__(**kwargs)
        self._max_lines = max_lines

    def compose(self):
        yield Static("Activity Log", id="log-title")
        yield RichLog(
            id="log-output",
            highlight=True,
            markup=True,
            max_lines=self._max_lines,
            wrap=True,
        )

    def write_line(self, text: str) -> None:
        """Append a line to the log output."""
        try:
            log = self.query_one("#log-output", RichLog)
            log.write(text)
        except Exception:
            pass

    def clear(self) -> None:
        """Clear the log output."""
        try:
            log = self.query_one("#log-output", RichLog)
            log.clear()
        except Exception:
            pass
