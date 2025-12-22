"""Inline selection widget for prompts - Mistral Vibe style.

This widget replaces the search input at the bottom of the screen to present
selection prompts inline, keeping the chat context visible. Uses the "bottom
app swapping" pattern from Mistral Vibe rather than modal overlays.
"""

from typing import ClassVar

from rich.text import Text
from textual import events
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

LAVENDER = "#b7a8e4"


class InlineSelector(Vertical):
    """Inline selection widget that replaces the input area.

    Key features (following Mistral Vibe pattern):
    - Replaces search input, not overlays it
    - Focus is captured via can_focus + on_blur
    - Communicates via Message subclasses
    - Keyboard navigation with visual feedback
    """

    can_focus = True
    can_focus_children = False

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
    InlineSelector {
        height: auto;
        min-height: 5;
        max-height: 12;
        margin: 0 1 1 1;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }

    InlineSelector:focus {
        border: solid $accent-lighten-2;
    }

    InlineSelector #selector-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    InlineSelector .option {
        padding: 0 1;
    }

    InlineSelector .option.selected {
        color: cyan;
        text-style: bold;
    }

    InlineSelector #selector-hints {
        margin-top: 1;
    }
    """

    class OptionSelected(Message):
        """Posted when an option is selected."""

        def __init__(self, value: str, label: str) -> None:
            self.value = value
            self.label = label
            super().__init__()

    class SelectionCancelled(Message):
        """Posted when selection is cancelled (ESC)."""

        pass

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        default_index: int = 0,
        **kwargs,
    ) -> None:
        """Initialize inline selector.

        Args:
            title: Prompt title text
            options: List of (value, display_text) tuples
            default_index: Initially selected option index
        """
        super().__init__(**kwargs)
        self._title = title
        self._options = options
        self._selected_index = default_index
        self._option_widgets: list[Static] = []

    def compose(self):
        """Compose the selector UI."""
        yield Static(self._title, id="selector-title")

        # Create static widgets for each option
        for i, (value, label) in enumerate(self._options):
            widget = Static("", classes="option")
            self._option_widgets.append(widget)
            yield widget

        # Hints
        hints = Text()
        hints.append("↑↓", style=LAVENDER)
        hints.append(" navigate  ", style="dim")
        hints.append("Enter", style=LAVENDER)
        hints.append(" select  ", style="dim")
        hints.append("ESC", style=LAVENDER)
        hints.append(" cancel", style="dim")
        yield Static(hints, id="selector-hints")

    def on_mount(self) -> None:
        """Focus self and update display on mount."""
        self._update_display()
        self.focus()

    def on_blur(self, event: events.Blur) -> None:
        """Recapture focus to prevent escape during selection."""
        self.call_after_refresh(self.focus)

    def _update_display(self) -> None:
        """Update option displays with current selection state."""
        for i, widget in enumerate(self._option_widgets):
            value, label = self._options[i]
            if i == self._selected_index:
                widget.update(f"[bold cyan]› {label}[/bold cyan]")
                widget.add_class("selected")
            else:
                widget.update(f"[dim]  {label}[/dim]")
                widget.remove_class("selected")

    def action_move_up(self) -> None:
        """Move selection up (with wrap-around)."""
        self._selected_index = (self._selected_index - 1) % len(self._options)
        self._update_display()

    def action_move_down(self) -> None:
        """Move selection down (with wrap-around)."""
        self._selected_index = (self._selected_index + 1) % len(self._options)
        self._update_display()

    def action_select(self) -> None:
        """Select the current option."""
        if self._options:
            value, label = self._options[self._selected_index]
            self.post_message(self.OptionSelected(value, label))

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
        """Cancel selection."""
        self.post_message(self.SelectionCancelled())
