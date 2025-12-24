"""Status bar widget for bottom of screen."""

from pathlib import Path

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing status, path, and file count.

    Layout:
        : Ready                              ~/repos/project  42 files
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 2;
        dock: bottom;
    }
    """

    def __init__(
        self,
        project_path: Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_path = project_path or Path.cwd()
        self._status = "Ready"
        self._status_style = "green"
        self._file_count: int | None = None
        self._is_initialized = False
        self._indexing_progress: float | None = None
        self._indexing_current: int = 0
        self._indexing_total: int = 0

    def update(
        self,
        status: str | None = None,
        status_style: str | None = None,
        file_count: int | None = None,
        is_initialized: bool | None = None,
        indexing_progress: float | None = None,
    ) -> None:
        """Update status bar state.

        Args:
            status: Status text (e.g., "Ready", "Searching", "Indexing")
            status_style: Rich style for status (e.g., "green", "yellow")
            file_count: Number of indexed files
            is_initialized: Whether project is initialized
            indexing_progress: Indexing progress (0.0-1.0) or None
        """
        if status is not None:
            self._status = status
        if status_style is not None:
            self._status_style = status_style
        if file_count is not None:
            self._file_count = file_count
        if is_initialized is not None:
            self._is_initialized = is_initialized
        if indexing_progress is not None:
            self._indexing_progress = indexing_progress
        self.refresh()

    def set_ready(self) -> None:
        """Set status to ready state."""
        self._status = "Ready"
        self._status_style = "green"
        self._indexing_progress = None
        self.refresh()

    def set_searching(self) -> None:
        """Set status to searching state."""
        self._status = "Searching..."
        self._status_style = "cyan"
        self.refresh()

    def set_indexing(
        self,
        progress: float = 0.0,
        current: int = 0,
        total: int = 0,
    ) -> None:
        """Set status to indexing state with file counts.

        Args:
            progress: Indexing progress (0.0 to 1.0)
            current: Current file number being processed
            total: Total files to process
        """
        self._status = "Indexing"
        self._status_style = "yellow"
        self._indexing_progress = progress
        self._indexing_current = current
        self._indexing_total = total
        self.refresh()

    def set_not_initialized(self) -> None:
        """Set status to not initialized state."""
        self._status = "Not initialized"
        self._status_style = "yellow"
        self._is_initialized = False
        self.refresh()

    def set_status(self, message: str, style: str = "yellow") -> None:
        """Set a temporary status message.

        Args:
            message: Status message to display
            style: Rich style for the message (default: yellow)
        """
        self._status = message
        self._status_style = style
        self._indexing_progress = None
        self.refresh()

    def render(self) -> RenderableType:
        # Left side: Status indicator
        left = Text()
        left.append(": ", style="dim")
        if self._indexing_progress is not None:
            pct = f" {self._indexing_progress * 100:.0f}%"
            # Show file counts: "Indexing 37% (15/40 files)"
            if self._indexing_total > 0:
                left.append(
                    f"{self._status}{pct} ({self._indexing_current}/{self._indexing_total} files)",
                    style=self._status_style,
                )
            else:
                left.append(self._status + pct, style=self._status_style)
        else:
            left.append(self._status, style=self._status_style)

        # Right side: Path and file count
        right = Text()
        right.append(self._get_abbreviated_path(), style="blue dim")
        right.append("  ")
        right.append(self._get_file_info(), style="dim")

        # Use Table.grid() for automatic width handling
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)  # Left expands to fill space
        grid.add_column(justify="right")  # Right fixed, right-aligned
        grid.add_row(left, right)

        return grid

    def _get_abbreviated_path(self) -> str:
        """Get the full project path."""
        return str(self._project_path)

    def _get_file_info(self) -> str:
        """Get file count info string."""
        if not self._is_initialized:
            return "no index"
        if self._file_count is not None:
            return f"{self._file_count} files"
        return ""
