"""Modal selection screen for prompts."""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

LAVENDER = "#b7a8e4"


class SelectionScreen(ModalScreen[str | None]):
    """Modal screen for selection prompts.

    Uses Textual's ModalScreen which automatically handles focus isolation -
    when pushed, it captures all keyboard input until dismissed.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("1", "select_1", show=False),
        Binding("2", "select_2", show=False),
        Binding("3", "select_3", show=False),
    ]

    DEFAULT_CSS = """
    SelectionScreen {
        align: center middle;
    }
    #selection-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    #selection-dialog #prompt-title {
        color: cyan;
        margin-bottom: 1;
    }
    #selection-dialog #options-display {
        padding: 0 1;
    }
    #selection-dialog #prompt-hints {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        default_index: int = 0,
    ) -> None:
        """Initialize selection screen.

        Args:
            title: Prompt title text
            options: List of (value, display_text) tuples
            default_index: Initially selected option index
        """
        super().__init__()
        self._title = title
        self._options = options
        self._selected_index = default_index

    def compose(self) -> ComposeResult:
        """Compose the selection dialog."""
        with Container(id="selection-dialog"):
            yield Static(self._title, id="prompt-title")
            yield Static("", id="options-display")
            # Hints with Rich markup
            hints = Text()
            hints.append("↑↓", style=LAVENDER)
            hints.append(" navigate  ", style="dim")
            hints.append("Enter", style=LAVENDER)
            hints.append(" select  ", style="dim")
            hints.append("ESC", style=LAVENDER)
            hints.append(" cancel", style="dim")
            yield Static(hints, id="prompt-hints")

    def on_mount(self) -> None:
        """Update display when mounted."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the options display with current selection."""
        display = self.query_one("#options-display", Static)
        lines = []
        for i, (value, label) in enumerate(self._options):
            if i == self._selected_index:
                lines.append(f"[bold cyan]› {label}[/bold cyan]")
            else:
                lines.append(f"[dim]  {label}[/dim]")
        display.update("\n".join(lines))

    def action_move_up(self) -> None:
        """Move selection up (with wrap-around)."""
        self._selected_index = (self._selected_index - 1) % len(self._options)
        self._update_display()

    def action_move_down(self) -> None:
        """Move selection down (with wrap-around)."""
        self._selected_index = (self._selected_index + 1) % len(self._options)
        self._update_display()

    def action_select(self) -> None:
        """Select the current option and dismiss."""
        if self._options:
            value, _ = self._options[self._selected_index]
            self.dismiss(value)

    def action_select_1(self) -> None:
        """Quick select option 1."""
        if len(self._options) >= 1:
            self._selected_index = 0
            self._update_display()
            self.action_select()

    def action_select_2(self) -> None:
        """Quick select option 2."""
        if len(self._options) >= 2:
            self._selected_index = 1
            self._update_display()
            self.action_select()

    def action_select_3(self) -> None:
        """Quick select option 3."""
        if len(self._options) >= 3:
            self._selected_index = 2
            self._update_display()
            self.action_select()

    def action_cancel(self) -> None:
        """Cancel selection and dismiss."""
        self.dismiss(None)
