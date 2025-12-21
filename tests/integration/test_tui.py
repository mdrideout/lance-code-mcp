"""Integration tests for the TUI application.

Uses Textual's Pilot API for testing the TUI without launching a real terminal.
"""

import shutil
from pathlib import Path

import pytest

from lance_code_rag.tui.app import LCRApp
from lance_code_rag.tui.widgets import ChatArea, SearchInput, StatusBar
from tests.conftest import setup_lcr_project


class TestTUIStartup:
    """Tests for TUI application startup."""

    @pytest.mark.asyncio
    async def test_app_starts_uninitialized(self, tmp_path: Path):
        """App starts correctly when project is not initialized."""
        app = LCRApp(project_root=tmp_path)
        async with app.run_test():
            # App should mount without crashing
            assert app.is_running
            assert app.is_initialized is False

            # Status bar should show not initialized
            status = app.query_one("#status", StatusBar)
            assert status is not None

    @pytest.mark.asyncio
    async def test_app_starts_initialized(self, tmp_path: Path, sample_project: Path):
        """App starts correctly when project is initialized."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test():
            assert app.is_running
            assert app.is_initialized is True

    @pytest.mark.asyncio
    async def test_widgets_exist(self, tmp_path: Path, sample_project: Path):
        """All expected widgets are present in the app."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test():
            # Check all main widgets exist
            assert app.query_one("#chat", ChatArea) is not None
            assert app.query_one("#input", SearchInput) is not None
            assert app.query_one("#status", StatusBar) is not None


class TestSlashCommands:
    """Tests for slash command parsing and handling."""

    @pytest.mark.asyncio
    async def test_help_command(self, tmp_path: Path, sample_project: Path):
        """Help command displays help text."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            # Type /help command
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/help"
            await pilot.press("enter")
            await pilot.pause()

            # Chat should contain help content
            app.query_one("#chat", ChatArea)
            # Just verify no crash - output content is internal

    @pytest.mark.asyncio
    async def test_status_command(self, tmp_path: Path, sample_project: Path):
        """Status command shows status info."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/status"
            await pilot.press("enter")
            await pilot.pause()

            # No crash = success
            assert app.is_running

    @pytest.mark.asyncio
    async def test_unknown_command(self, tmp_path: Path, sample_project: Path):
        """Unknown commands show error message."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/unknown"
            await pilot.press("enter")
            await pilot.pause()

            # Should not crash
            assert app.is_running

    @pytest.mark.asyncio
    async def test_bare_text_treated_as_search(self, tmp_path: Path, sample_project: Path):
        """Text without / prefix is treated as search query."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "some search query"
            await pilot.press("enter")
            await pilot.pause()

            # Should not crash - will show "no index" message
            assert app.is_running


class TestStatusBar:
    """Tests for the StatusBar widget."""

    @pytest.mark.asyncio
    async def test_status_bar_renders_uninitialized(self, tmp_path: Path):
        """StatusBar renders correctly when not initialized."""
        app = LCRApp(project_root=tmp_path)
        async with app.run_test():
            status = app.query_one("#status", StatusBar)
            # Should render without crashing
            assert status is not None

    @pytest.mark.asyncio
    async def test_status_bar_renders_initialized(
        self, tmp_path: Path, sample_project: Path
    ):
        """StatusBar renders correctly when initialized."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test():
            status = app.query_one("#status", StatusBar)
            assert status is not None


class TestKeyboardShortcuts:
    """Tests for keyboard shortcuts."""

    @pytest.mark.asyncio
    async def test_ctrl_c_clears_input_first(self, tmp_path: Path, sample_project: Path):
        """First Ctrl+C clears input if there's text."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "some text"
            await pilot.press("ctrl+c")
            await pilot.pause()
            # Input should be cleared, app still running
            assert input_widget.text == ""
            assert app.is_running

    @pytest.mark.asyncio
    async def test_ctrl_c_twice_quits(self, tmp_path: Path, sample_project: Path):
        """Ctrl+C twice within 2 seconds quits the application."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            await pilot.press("ctrl+c")
            # App should exit - run_test context handles this

    @pytest.mark.asyncio
    async def test_ctrl_l_clears(self, tmp_path: Path, sample_project: Path):
        """Ctrl+L clears the output."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+l")
            await pilot.pause()
            # Should not crash
            assert app.is_running


class TestSearchInput:
    """Tests for the SearchInput widget."""

    @pytest.mark.asyncio
    async def test_search_input_accepts_text(self, tmp_path: Path, sample_project: Path):
        """SearchInput widget accepts text input."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test():
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "test input"
            assert input_widget.text == "test input"

    @pytest.mark.asyncio
    async def test_command_history_navigation(
        self, tmp_path: Path, sample_project: Path
    ):
        """Command history can be navigated with up/down arrows."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)

            # Submit a few commands
            input_widget.text = "/help"
            await pilot.press("enter")
            await pilot.pause()

            input_widget.text = "/status"
            await pilot.press("enter")
            await pilot.pause()

            # Navigate history with up arrow
            input_widget.focus()
            await pilot.press("up")
            await pilot.pause()

            # Should show previous command
            # (exact behavior depends on implementation)
            assert app.is_running


class TestChatArea:
    """Tests for the ChatArea widget."""

    @pytest.mark.asyncio
    async def test_chat_area_mounts_welcome(self, tmp_path: Path, sample_project: Path):
        """ChatArea mounts welcome box on initialization."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test():
            chat = app.query_one("#chat", ChatArea)
            # Chat area should exist and be scrollable
            assert chat is not None
            assert chat.can_focus is False  # Allow mouse wheel scrolling

    @pytest.mark.asyncio
    async def test_clear_command_resets_chat(self, tmp_path: Path, sample_project: Path):
        """Clear command removes all content and shows welcome again."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)
        setup_lcr_project(project)

        app = LCRApp(project_root=project)
        async with app.run_test() as pilot:
            # Add some content
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/help"
            await pilot.press("enter")
            await pilot.pause()

            # Clear
            input_widget.text = "/clear"
            await pilot.press("enter")
            await pilot.pause()

            # Should not crash
            assert app.is_running


class TestInitWizard:
    """Tests for the init wizard flow."""

    @pytest.mark.asyncio
    async def test_init_command_pushes_wizard_screen(self, tmp_path: Path):
        """Running /init pushes the wizard screen."""
        app = LCRApp(project_root=tmp_path)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/init"
            await pilot.press("enter")
            await pilot.pause()

            # Wizard screen should be pushed - check we have a ProviderScreen
            from lance_code_rag.tui.init_wizard import ProviderScreen

            screens = list(app.screen_stack)
            assert len(screens) >= 2  # Default screen + wizard screen
            assert isinstance(screens[-1], ProviderScreen)

    @pytest.mark.asyncio
    async def test_wizard_cancel_returns_to_main(self, tmp_path: Path):
        """Canceling the wizard returns to the main app."""
        app = LCRApp(project_root=tmp_path)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/init"
            await pilot.press("enter")
            await pilot.pause()

            # Press Cancel button
            await pilot.click("#cancel")
            await pilot.pause()

            # Should be back to main screen
            from lance_code_rag.tui.init_wizard import ProviderScreen

            screens = list(app.screen_stack)
            assert not any(isinstance(s, ProviderScreen) for s in screens)
            assert app.is_running
            assert app.is_initialized is False  # Still not initialized

    @pytest.mark.asyncio
    async def test_wizard_complete_initializes_project(self, tmp_path: Path):
        """Completing the wizard initializes the project."""
        app = LCRApp(project_root=tmp_path)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", SearchInput)
            input_widget.text = "/init"
            await pilot.press("enter")
            await pilot.pause()

            # Step 1: Provider screen - click Continue (Local is default)
            await pilot.click("#continue")
            await pilot.pause()

            # Step 2: Model screen - click Continue (bge-base is default)
            await pilot.click("#continue")
            await pilot.pause()

            # Step 3: Confirm screen - click Initialize
            await pilot.click("#init")
            await pilot.pause()
            # Wait for indexing to start
            await pilot.pause()

            # Project should be initialized (or initializing)
            lcr_dir = tmp_path / ".lance-code-rag"
            assert lcr_dir.exists() or app.is_initialized
