"""Message components for conversational TUI display."""

from rich.console import RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Static

from ...search import SearchResult, SearchResults


class UserQuery(Static):
    """Displays user input as '> query text'."""

    DEFAULT_CSS = """
    UserQuery {
        margin: 1 0 0 0;
        padding: 0 2;
    }
    """

    def __init__(self, query: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._query = query

    def render(self) -> RenderableType:
        text = Text()
        text.append("> ", style="bold cyan")
        text.append(self._query, style="bold")
        return text


class AssistantMessage(Static):
    """Displays assistant response with ● bullet prefix."""

    DEFAULT_CSS = """
    AssistantMessage {
        margin: 0 0 0 0;
        padding: 0 2;
    }
    """

    def __init__(self, message: str, style: str = "dim", **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._style = style

    def render(self) -> RenderableType:
        text = Text()
        text.append("● ", style="cyan")
        text.append(self._message, style=self._style)
        return text


class StatusMessage(Static):
    """Displays ✓ success or ✗ error messages."""

    DEFAULT_CSS = """
    StatusMessage {
        margin: 0 0 1 0;
        padding: 0 2;
    }
    """

    def __init__(
        self, message: str, success: bool = True, details: str | None = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._success = success
        self._details = details

    def render(self) -> RenderableType:
        text = Text()
        if self._success:
            text.append("✓ ", style="bold green")
            text.append(self._message, style="green")
        else:
            text.append("✗ ", style="bold red")
            text.append(self._message, style="red")

        if self._details:
            text.append(f" ({self._details})", style="dim")

        return text


class SearchResultItem(Static):
    """Displays a single search result with code preview."""

    DEFAULT_CSS = """
    SearchResultItem {
        margin: 0 0 1 2;
        padding: 0;
    }
    """

    def __init__(self, rank: int, result: SearchResult, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rank = rank
        self._result = result

    def render(self) -> RenderableType:
        result = self._result

        # Type colors
        type_colors = {
            "function": "green",
            "class": "blue",
            "method": "cyan",
            "module": "yellow",
        }
        color = type_colors.get(result.type, "white")

        # Header line: rank, type, name, score
        header = Text()
        header.append(f"{self._rank}. ", style="bold dim")
        header.append(result.type, style=color)
        if result.name:
            header.append(f" {result.name}", style="bold")
        header.append(f" ({result.score:.3f})", style="dim")
        header.append("\n")

        # File location
        header.append(f"   {result.filepath}", style="blue underline")
        header.append(f":{result.start_line}-{result.end_line}", style="dim")

        return header


class CodePreview(Static):
    """Displays a syntax-highlighted code preview in a bordered panel."""

    DEFAULT_CSS = """
    CodePreview {
        margin: 0 2 1 4;
        padding: 0;
    }
    """

    def __init__(self, code: str, filepath: str, max_lines: int = 5, **kwargs) -> None:
        super().__init__(**kwargs)
        self._code = code
        self._filepath = filepath
        self._max_lines = max_lines

    def render(self) -> RenderableType:
        # Truncate to max lines
        lines = self._code.split("\n")[: self._max_lines]
        preview = "\n".join(lines)
        if len(self._code.split("\n")) > self._max_lines:
            preview += "\n..."

        # Detect language from filepath
        ext = (
            self._filepath.rsplit(".", 1)[-1] if "." in self._filepath else "text"
        )
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "jsx": "javascript",
            "go": "go",
            "rs": "rust",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "h": "c",
            "hpp": "cpp",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
            "scala": "scala",
            "cs": "csharp",
        }
        lang = lang_map.get(ext, "text")

        syntax = Syntax(
            preview,
            lang,
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )

        return Panel(
            syntax,
            border_style="dim",
            padding=(0, 1),
        )


class SearchResultsDisplay(Static):
    """Container for displaying all search results."""

    DEFAULT_CSS = """
    SearchResultsDisplay {
        padding: 0 2;
    }
    """

    def __init__(self, results: SearchResults, **kwargs) -> None:
        super().__init__(**kwargs)
        self._results = results

    def compose(self):
        """Compose the search results display."""
        results = self._results

        # Status message
        if results.results:
            yield StatusMessage(
                f"Found {len(results.results)} results",
                success=True,
                details=f"{results.search_type}, {results.elapsed_ms:.0f}ms",
            )
        else:
            yield StatusMessage(
                "No results found",
                success=False,
                details=f"{results.elapsed_ms:.0f}ms",
            )
            return

        # Individual results
        for i, result in enumerate(results.results, 1):
            yield SearchResultItem(i, result)
            yield CodePreview(result.text, result.filepath)


class IndexingProgress(Static):
    """Shows indexing progress with spinner."""

    DEFAULT_CSS = """
    IndexingProgress {
        margin: 0 0 1 0;
        padding: 0 2;
    }
    """

    def __init__(self, message: str = "Indexing...", progress: float = 0.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._progress = progress

    def update_progress(self, progress: float, message: str | None = None) -> None:
        """Update the progress value and optionally the message."""
        self._progress = progress
        if message:
            self._message = message
        self.refresh()

    def render(self) -> RenderableType:
        text = Text()
        text.append("◐ ", style="bold yellow")  # Spinner character
        text.append(self._message, style="yellow")
        if self._progress > 0:
            text.append(f" {self._progress * 100:.0f}%", style="bold yellow")
        return text


class HelpDisplay(Static):
    """Displays help information."""

    DEFAULT_CSS = """
    HelpDisplay {
        margin: 1 0;
        padding: 0 2;
    }
    """

    def render(self) -> RenderableType:
        text = Text()
        text.append("Available Commands\n\n", style="bold underline")

        commands = [
            ("/search <query>", "Search the indexed codebase"),
            ("/index", "Index the codebase (incremental)"),
            ("/index --force", "Force full re-index"),
            ("/status", "Show index status and statistics"),
            ("/init", "Reinitialize with different settings"),
            ("/clean", "Remove .lance-code-rag directory"),
            ("/terminal-setup", "Configure Shift+Enter in VS Code"),
            ("/clear", "Clear the output"),
            ("/help", "Show this help message"),
            ("/quit", "Exit the application"),
        ]

        for cmd, desc in commands:
            text.append(f"  {cmd:<22}", style="cyan bold")
            text.append(f" {desc}\n")

        text.append("\nKeyboard Shortcuts:\n", style="bold underline")
        text.append("  Enter              ", style="dim")
        text.append("Submit query\n")
        text.append("  \\ + Enter          ", style="dim")
        text.append("New line (works everywhere)\n")
        text.append("  Shift/Alt+Enter    ", style="dim")
        text.append("New line (terminal-dependent)\n")
        text.append("  Up/Down            ", style="dim")
        text.append("Command history\n")
        text.append("  Ctrl+L             ", style="dim")
        text.append("Clear output\n")
        text.append("  Ctrl+C             ", style="dim")
        text.append("Exit\n")

        text.append("\nTip: ", style="bold yellow")
        text.append("Type any text without '/' to search directly.\n", style="dim")

        return Panel(text, title="Help", border_style="blue")
