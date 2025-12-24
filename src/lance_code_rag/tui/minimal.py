"""Minimal Textual TUI - flat widget hierarchy experiment.

This is a simplified version to test if scroll issues are caused by
our widget complexity. Uses ONLY:
- VerticalScroll (single container)
- Static (for all output - no compose())
- Input (stock widget)

If this works, we can expand it. If not, we move to prompt_toolkit.
"""

from pathlib import Path

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static


class MinimalApp(App):
    """Minimal TUI with flat widget hierarchy."""

    CSS = """
    Screen {
        layout: vertical;
        overflow: hidden;
    }

    VerticalScroll {
        height: 1fr;
        scrollbar-size-vertical: 1;
    }

    Input {
        height: 3;
        dock: bottom;
    }

    Static {
        height: auto;
        width: 100%;
        padding: 0 2;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self, project_root: Path | None = None):
        super().__init__()
        self.project_root = project_root or Path.cwd()

    def compose(self) -> ComposeResult:
        vs = VerticalScroll(id="output")
        vs.can_focus = False  # Elia pattern - helps with mouse scroll
        yield vs
        yield Input(placeholder="> Enter command or search query", id="input")

    def on_mount(self) -> None:
        self._show_welcome()
        self.query_one("#input", Input).focus()

    def _show_welcome(self) -> None:
        """Show welcome message."""
        welcome = Text()
        welcome.append("Lance Code RAG\n", style="bold cyan")
        welcome.append(f"Project: {self.project_root}\n", style="dim")
        welcome.append("\nType /help for commands, or just type to search.\n", style="dim")
        self._add_output(Panel(welcome, title="Welcome", border_style="cyan"))

    def _add_output(self, content) -> None:
        """Add any Rich renderable as a Static widget."""
        output = self.query_one("#output", VerticalScroll)
        output.mount(Static(content))
        output.scroll_end(animate=False)

    def _add_text(self, text: str, style: str = "") -> None:
        """Add simple text output."""
        self._add_output(Text(text, style=style))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        query = event.value.strip()
        if not query:
            return

        # Clear input first
        event.input.value = ""

        # Echo the query
        echo = Text()
        echo.append("> ", style="bold cyan")
        echo.append(query, style="bold")
        self._add_output(echo)

        # Parse and handle
        if query.startswith("/"):
            self._handle_command(query)
        else:
            self._handle_search(query)

    def _handle_command(self, command: str) -> None:
        """Handle slash commands."""
        parts = command[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            self._show_help()
        elif cmd == "quit" or cmd == "q":
            self.exit()
        elif cmd == "clear":
            self.action_clear()
        elif cmd == "search":
            if args:
                self._handle_search(args)
            else:
                self._add_text("Usage: /search <query>", style="yellow")
        elif cmd == "status":
            self._show_status()
        elif cmd == "scroll":
            # Debug: add lots of content to test scrolling
            self._add_scroll_test()
        else:
            self._add_text(f"Unknown command: /{cmd}", style="red")
            self._add_text("Type /help for available commands", style="dim")

    def _show_help(self) -> None:
        """Show help information."""
        help_text = Text()
        help_text.append("Available Commands\n\n", style="bold underline")

        commands = [
            ("/search <query>", "Search the codebase"),
            ("/status", "Show index status"),
            ("/clear", "Clear the output"),
            ("/scroll", "Add test content (debug)"),
            ("/help", "Show this help"),
            ("/quit", "Exit the application"),
        ]

        for cmd, desc in commands:
            help_text.append(f"  {cmd:<20}", style="cyan bold")
            help_text.append(f" {desc}\n")

        help_text.append("\nKeyboard Shortcuts\n", style="bold underline")
        help_text.append("  Ctrl+C              ", style="dim")
        help_text.append("Exit\n")
        help_text.append("  Ctrl+L              ", style="dim")
        help_text.append("Clear output\n")

        help_text.append("\nTip: ", style="bold yellow")
        help_text.append("Type any text without '/' to search directly.\n", style="dim")

        self._add_output(Panel(help_text, title="Help", border_style="blue"))

    def _show_status(self) -> None:
        """Show status information."""
        table = Table(title="Status", border_style="blue")
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Project", str(self.project_root))
        table.add_row("Initialized", "Checking...")
        table.add_row("Index", "Not loaded")

        self._add_output(table)

    def _handle_search(self, query: str) -> None:
        """Handle search query."""
        status = Text()
        status.append("● ", style="cyan")
        status.append(f"Searching for '{query}'...", style="dim")
        self._add_output(status)

        # Placeholder for actual search
        result = Text()
        result.append("✓ ", style="green bold")
        result.append("Search not implemented in minimal mode", style="dim")
        self._add_output(result)

    def _add_scroll_test(self) -> None:
        """Add test content to verify scrolling works."""
        self._add_text("Adding 50 lines of test content...", style="yellow")

        for i in range(1, 51):
            self._add_text(f"  Line {i:02d}: Test content for scroll verification")

        self._add_text("Done! Try scrolling with mouse wheel.", style="green")

    def action_clear(self) -> None:
        """Clear the output area."""
        self.query_one("#output", VerticalScroll).remove_children()
        self._show_welcome()

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


def run_minimal(project_root: Path | None = None) -> None:
    """Run the minimal TUI application."""
    app = MinimalApp(project_root=project_root)
    app.run()


if __name__ == "__main__":
    run_minimal()
