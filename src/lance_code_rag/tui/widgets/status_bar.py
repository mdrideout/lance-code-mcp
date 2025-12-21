"""Status bar widget for bottom of screen."""

from pathlib import Path

from rich.console import RenderableType
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

    def set_indexing(self, progress: float = 0.0) -> None:
        """Set status to indexing state.

        Args:
            progress: Indexing progress (0.0 to 1.0)
        """
        self._status = "Indexing..."
        self._status_style = "yellow"
        self._indexing_progress = progress
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
        text = Text()

        # Left: Status indicator
        text.append(": ", style="dim")

        # Status with optional progress
        if self._indexing_progress is not None:
            pct = f" {self._indexing_progress * 100:.0f}%"
            text.append(self._status + pct, style=self._status_style)
        else:
            text.append(self._status, style=self._status_style)

        # Calculate spacing for right-aligned content
        # We'll use a simple approach - pad with spaces
        path_str = self._get_abbreviated_path()
        file_info = self._get_file_info()

        # Build right side
        right_side = f"{path_str}  {file_info}"

        # Get available width (approximate - we'll pad generously)
        left_len = len(": ") + len(self._status)
        if self._indexing_progress is not None:
            left_len += 5  # " 100%"

        # Pad to push right side to the end
        # Use a reasonable terminal width assumption
        total_width = 80
        padding = max(1, total_width - left_len - len(right_side))
        text.append(" " * padding)

        # Right: Path and file count
        text.append(path_str, style="blue dim")
        text.append("  ")
        text.append(file_info, style="dim")

        return text

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
