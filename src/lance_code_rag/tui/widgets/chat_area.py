"""Chat area widget for displaying conversational flow."""

from pathlib import Path

from textual.containers import VerticalScroll

from ...config import LCRConfig
from ...manifest import ManifestStats
from ...search import SearchResults
from .messages import (
    AssistantMessage,
    HelpDisplay,
    IndexingProgress,
    SearchResultsDisplay,
    StatusMessage,
    UserQuery,
)
from .welcome_box import WelcomeBox


class ChatArea(VerticalScroll):
    """Main scrollable content area with conversational message flow.

    Displays welcome box initially, then appends user queries and responses.
    """

    # Allow mouse wheel scrolling without needing focus
    can_focus = False

    DEFAULT_CSS = """
    ChatArea {
        height: 1fr;
        padding: 1 0;
    }
    """

    def __init__(
        self,
        project_path: Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_path = project_path or Path.cwd()
        self._welcome_box: WelcomeBox | None = None
        self._indexing_widget: IndexingProgress | None = None

    def show_welcome(
        self,
        config: LCRConfig | None = None,
        stats: ManifestStats | None = None,
        is_initialized: bool = False,
    ) -> None:
        """Display the welcome box with project info.

        Args:
            config: Current LCR configuration
            stats: Manifest statistics
            is_initialized: Whether the project is initialized
        """
        provider = config.embedding_provider if config else None
        model = config.embedding_model if config else None
        file_count = stats.total_files if stats else None

        self._welcome_box = WelcomeBox(
            provider=provider,
            model=model,
            file_count=file_count,
            project_path=self._project_path,
            is_initialized=is_initialized,
        )
        self.mount(self._welcome_box)

    def update_welcome(
        self,
        config: LCRConfig | None = None,
        stats: ManifestStats | None = None,
        is_initialized: bool | None = None,
    ) -> None:
        """Update the welcome box info without recreating it."""
        if self._welcome_box:
            self._welcome_box.update_info(
                provider=config.embedding_provider if config else None,
                model=config.embedding_model if config else None,
                file_count=stats.total_files if stats else None,
                is_initialized=is_initialized,
            )

    def show_user_query(self, query: str) -> None:
        """Display a user query.

        Args:
            query: The user's query text
        """
        self.mount(UserQuery(query))
        self.scroll_end()

    def show_assistant_message(self, message: str, style: str = "dim") -> None:
        """Display an assistant message with bullet prefix.

        Args:
            message: Message text
            style: Rich style for the message
        """
        self.mount(AssistantMessage(message, style))
        self.scroll_end()

    def show_status(self, message: str, success: bool = True, details: str | None = None) -> None:
        """Display a status message (success or error).

        Args:
            message: Status message
            success: True for success (green ✓), False for error (red ✗)
            details: Optional details in parentheses
        """
        self.mount(StatusMessage(message, success, details))
        self.scroll_end()

    def show_search_results(self, results: SearchResults) -> None:
        """Display search results.

        Args:
            results: SearchResults from the search engine
        """
        self.mount(SearchResultsDisplay(results))
        self.scroll_end()

    def show_help(self) -> None:
        """Display help information."""
        self.mount(HelpDisplay())
        self.scroll_end()

    def start_indexing(self, message: str = "Indexing...") -> None:
        """Show indexing progress indicator.

        Args:
            message: Initial message to display
        """
        self._indexing_widget = IndexingProgress(message)
        self.mount(self._indexing_widget)
        self.scroll_end()

    def update_indexing(self, progress: float, message: str | None = None) -> None:
        """Update indexing progress.

        Args:
            progress: Progress value (0.0 to 1.0)
            message: Optional new message
        """
        if self._indexing_widget:
            self._indexing_widget.update_progress(progress, message)

    def finish_indexing(self, success: bool = True, message: str = "Indexing complete") -> None:
        """Complete indexing and show result.

        Args:
            success: Whether indexing succeeded
            message: Completion message
        """
        if self._indexing_widget:
            self._indexing_widget.remove()
            self._indexing_widget = None

        self.mount(StatusMessage(message, success=success))
        self.scroll_end()

    def clear(self) -> None:
        """Clear all content and re-show welcome box."""
        self.remove_children()
        self._indexing_widget = None
        self._welcome_box = None
