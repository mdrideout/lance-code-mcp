"""Welcome box widget with gradient banner and project info."""

from pathlib import Path

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

from lance_code_rag import __version__

from ..banner import BANNER_ASCII, create_gradient_banner


class WelcomeBox(Static):
    """Welcome banner with gradient animation and project info.

    Shows:
    - Gradient ASCII banner
    - Version, provider, model info
    - Current directory
    - Help hints
    """

    DEFAULT_CSS = """
    WelcomeBox {
        margin: 0 0 1 0;
        padding: 0;
    }
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        file_count: int | None = None,
        project_path: Path | None = None,
        is_initialized: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._provider = provider
        self._model = model
        self._file_count = file_count
        self._project_path = project_path or Path.cwd()
        self._is_initialized = is_initialized

    def render(self) -> RenderableType:
        # Gradient banner - centered, no left border
        banner_text = create_gradient_banner(BANNER_ASCII, show_info=False, center=True)

        # Info line: version + provider + model + file count
        info_parts = [f"v{__version__}"]

        if self._is_initialized and self._provider:
            info_parts.append(self._provider)

            if self._model:
                # Truncate long model names
                model_display = self._model
                if len(model_display) > 25:
                    model_display = model_display[:22] + "..."
                info_parts.append(model_display)

            if self._file_count is not None:
                info_parts.append(f"{self._file_count} files")

        info_text = Text(" · ".join(info_parts), style="dim")

        # Current directory (full path)
        path_text = Text(str(self._project_path), style="blue")

        # Help hints
        hint = Text()
        if self._is_initialized:
            hint.append("Type ")
            hint.append("/help", style="bold cyan")
            hint.append(" for commands · ")
            hint.append("/init", style="bold cyan")
            hint.append(" to reconfigure")
        else:
            hint.append("Run ")
            hint.append("/init", style="bold cyan")
            hint.append(" to set up lance-code-rag")

        # Combine with centering
        content = Group(
            Align.center(banner_text),
            Align.center(info_text),
            Align.center(path_text),
            Text(),  # Empty line for spacing
            Align.center(hint),
        )

        return Panel(
            content,
            border_style="dim",
            padding=(0, 1),
        )

    def update_info(
        self,
        provider: str | None = None,
        model: str | None = None,
        file_count: int | None = None,
        is_initialized: bool | None = None,
    ) -> None:
        """Update the displayed info and refresh."""
        if provider is not None:
            self._provider = provider
        if model is not None:
            self._model = model
        if file_count is not None:
            self._file_count = file_count
        if is_initialized is not None:
            self._is_initialized = is_initialized
        self.refresh()
