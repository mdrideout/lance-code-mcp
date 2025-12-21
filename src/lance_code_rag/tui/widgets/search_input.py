"""Search input widget with multiline support and auto-grow."""

import time
from dataclasses import dataclass

from textual import on
from textual.binding import Binding
from textual.events import Key
from textual.message import Message
from textual.widgets import TextArea


@dataclass
class SlashCommand:
    """Parsed slash command."""

    command: str  # e.g., "/init", "/search", "/index"
    args: str  # everything after the command


class SearchInput(TextArea):
    """Multiline input widget with auto-grow and command support.

    Features:
    - Enter submits the input
    - Backslash + Enter adds newline (works in all terminals)
    - Shift+Enter, Alt+Enter, or Ctrl+J also add newline (terminal-dependent)
    - Auto-grows up to 5 lines
    - Recognizes slash commands like /init, /search, /index
    - Bare text (no slash) is treated as a search query
    """

    COMMANDS = {
        "/init": "Initialize lance-code-rag in this project",
        "/index": "Index the codebase (--force to rebuild)",
        "/search": "Search codebase: /search <query>",
        "/status": "Show index status and statistics",
        "/clean": "Remove .lance-code-rag directory",
        "/help": "Show available commands",
        "/clear": "Clear the output",
        "/quit": "Exit the application",
    }

    BINDINGS = [
        Binding("enter", "submit", "Submit", show=False),
        # Note: ESC is handled in on_key() for ESC+Enter newline detection
        # (used by /terminal-setup which sends \u001b\r for Shift+Enter)
    ]

    DEFAULT_CSS = """
    SearchInput {
        height: auto;
        min-height: 3;
        max-height: 7;
        margin: 0 1 1 1;
        border: solid $accent;
        padding: 0 1;
        background: $surface;
    }

    SearchInput:focus {
        border: solid $accent-lighten-2;
    }
    """

    class CommandSubmitted(Message):
        """Posted when a command is submitted."""

        def __init__(self, command: SlashCommand) -> None:
            self.command = command
            super().__init__()

    # Keys that insert a newline instead of submitting
    # - shift+enter: Native in terminals with proper key reporting
    # - alt+enter: Works in most terminals
    # - ctrl+j: Universal fallback (line feed character)
    # Note: Backslash+Enter is handled separately in on_key()
    NEWLINE_KEYS = {"shift+enter", "alt+enter", "ctrl+j"}

    def __init__(self, **kwargs) -> None:
        # Remove any conflicting kwargs before passing to parent
        kwargs.pop("placeholder", None)
        super().__init__(
            language=None,  # Plain text, no syntax highlighting
            soft_wrap=True,
            show_line_numbers=False,
            tab_behavior="focus",  # Tab moves focus, not indent
            **kwargs,
        )
        self._history: list[str] = []
        self._history_index: int = -1
        self._placeholder = "Search code..."
        # Track ESC key timing for ESC+Enter newline detection
        # (used by /terminal-setup which sends \u001b\r for Shift+Enter)
        self._escape_pressed_time: float = 0.0

    def on_mount(self) -> None:
        """Show placeholder when mounted."""
        self._update_placeholder()

    def _update_placeholder(self) -> None:
        """Update placeholder visibility based on content."""
        # TextArea doesn't have built-in placeholder, so we manage it ourselves
        pass

    @on(TextArea.Changed)
    def _on_text_changed(self, event: TextArea.Changed) -> None:
        """Handle text changes for placeholder management."""
        self._update_placeholder()

    def _char_before_cursor(self) -> str:
        """Get the character immediately before the cursor position."""
        row, col = self.cursor_location
        if col == 0:
            return ""
        lines = self.text.split("\n")
        if row < len(lines) and col <= len(lines[row]):
            return lines[row][col - 1]
        return ""

    def on_key(self, event: Key) -> None:
        """Handle key events for submit and history navigation."""
        # Track ESC key timing for ESC+Enter detection
        # VS Code's /terminal-setup sends \u001b\r for Shift+Enter
        if event.key == "escape":
            self._escape_pressed_time = time.monotonic()
            # Don't prevent default - let blur happen if no Enter follows
            return

        # Check if this key (or any of its aliases) is a newline key
        keys_to_check = {event.key} | set(getattr(event, "aliases", []))
        if keys_to_check & self.NEWLINE_KEYS:
            self.insert("\n")
            event.prevent_default()
            event.stop()
            return

        # Handle Enter key
        if event.key == "enter":
            # ESC+Enter detection: if ESC was pressed within 100ms, treat as newline
            # This is how /terminal-setup works - sends \u001b\r for Shift+Enter
            if time.monotonic() - self._escape_pressed_time < 0.1:
                self.insert("\n")
                event.prevent_default()
                event.stop()
                return

            # Backslash-escape: if character before cursor is \, treat as newline
            # This is the Claude Code approach - works in all terminals
            if self._char_before_cursor() == "\\":
                # Explicitly rebuild text with backslash removed and newline inserted
                # (Using action_delete_left + insert doesn't reliably position cursor)
                row, col = self.cursor_location
                lines = self.text.split("\n")
                current_line = lines[row]

                # Split: content before backslash | content after cursor
                before_backslash = current_line[: col - 1]
                after_cursor = current_line[col:]

                # Rebuild lines: replace current line with split + insert new line
                new_lines = lines[:row] + [before_backslash, after_cursor] + lines[row + 1 :]

                # Update text and move cursor to start of new line
                self.text = "\n".join(new_lines)
                self.move_cursor((row + 1, 0))

                event.prevent_default()
                event.stop()
                return

            # Plain Enter submits
            self._submit()
            event.prevent_default()
            event.stop()
            return

        # History navigation
        if event.key == "up":
            # History navigation only when at first line
            if self._is_cursor_at_first_line():
                self._navigate_history_up()
                event.prevent_default()
        elif event.key == "down":
            # History navigation only when at last line
            if self._is_cursor_at_last_line():
                self._navigate_history_down()
                event.prevent_default()

    def _is_cursor_at_first_line(self) -> bool:
        """Check if cursor is on the first line."""
        row, _ = self.cursor_location
        return row == 0

    def _is_cursor_at_last_line(self) -> bool:
        """Check if cursor is on the last line."""
        row, _ = self.cursor_location
        lines = self.text.split("\n")
        return row >= len(lines) - 1

    def _submit(self) -> None:
        """Submit the current text as a command."""
        text = self.text.strip()
        if not text:
            return

        # Add to history
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_index = -1

        # Parse command
        if text.startswith("/"):
            # Extract command and args from first line or entire text
            lines = text.split("\n", 1)
            first_line = lines[0]
            parts = first_line.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            # If multiline, append rest of text to args
            if len(lines) > 1:
                args = args + "\n" + lines[1] if args else lines[1]
            self.post_message(self.CommandSubmitted(SlashCommand(cmd, args)))
        else:
            # Treat bare text as search
            self.post_message(self.CommandSubmitted(SlashCommand("/search", text)))

        # Clear input
        self.clear()

    def _navigate_history_up(self) -> None:
        """Navigate to previous command in history."""
        if self._history and self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.text = self._history[-(self._history_index + 1)]
            # Move cursor to end
            self.move_cursor((0, len(self.text)))

    def _navigate_history_down(self) -> None:
        """Navigate to next command in history."""
        if self._history_index > 0:
            self._history_index -= 1
            self.text = self._history[-(self._history_index + 1)]
            self.move_cursor((0, len(self.text)))
        elif self._history_index == 0:
            self._history_index = -1
            self.clear()

    def action_submit(self) -> None:
        """Action to submit the input."""
        self._submit()

    def action_blur(self) -> None:
        """Action to blur the input."""
        self.screen.focus_next()
