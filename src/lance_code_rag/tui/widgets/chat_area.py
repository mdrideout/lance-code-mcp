"""Chat area widget for displaying conversational flow."""

from pathlib import Path

from textual.containers import VerticalScroll
from textual.css.query import NoMatches

from ...config import LCRConfig
from ...manifest import ManifestStats
from ...search import SearchResults
from .messages import (
    AssistantMessage,
    HelpDisplay,
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

    async def show_welcome(
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
        # Remove existing welcome box if present (avoids duplicate ID error)
        try:
            existing = self.query_one("#welcome", WelcomeBox)
            await existing.remove()
        except NoMatches:
            pass

        provider = config.embedding_provider if config else None
        model = config.embedding_model if config else None
        file_count = stats.total_files if stats else None

        welcome = WelcomeBox(
            provider=provider,
            model=model,
            file_count=file_count,
            project_path=self._project_path,
            is_initialized=is_initialized,
            id="welcome",
        )
        await self.mount(welcome)

    def update_welcome(
        self,
        config: LCRConfig | None = None,
        stats: ManifestStats | None = None,
        is_initialized: bool | None = None,
    ) -> None:
        """Update the welcome box info without recreating it."""
        try:
            welcome = self.query_one("#welcome", WelcomeBox)
            welcome.update_info(
                provider=config.embedding_provider if config else None,
                model=config.embedding_model if config else None,
                file_count=stats.total_files if stats else None,
                is_initialized=is_initialized,
            )
        except NoMatches:
            pass  # Welcome box not shown

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

    def start_indexing(self, message: str = "Indexing started") -> None:
        """Show simple indexing started message.

        Progress updates are shown in the status bar, not the chat area.

        Args:
            message: Message to display
        """
        self.mount(StatusMessage(message, success=True))
        self.scroll_end()

    def finish_indexing(self, success: bool = True, message: str | None = None) -> None:
        """Complete indexing silently on success, show error on failure.

        On success: Silent - status bar already shows Ready.
        On failure: Show error message in chat.

        Args:
            success: Whether indexing succeeded
            message: Error message (only shown on failure)
        """
        # Only show message on error
        if not success and message:
            self.mount(StatusMessage(message, success=False))
            self.scroll_end()

    def clear(self) -> None:
        """Clear all content and re-show welcome box."""
        self.remove_children()
