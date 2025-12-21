"""Main TUI application for Lance Code RAG - Mistral Vibe style."""

import asyncio
import shutil
import time
from pathlib import Path

from rich.table import Table
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive

from .. import LCR_DIR
from ..config import LCRConfig, get_lcr_dir, load_config, save_config
from ..indexer import run_index
from ..manifest import Manifest, create_empty_manifest, load_manifest, save_manifest
from ..search import SearchEngine, SearchError
from .init_wizard import InitWizardApp, WizardResult
from .widgets import ChatArea, SearchInput, StatusBar


class LCRApp(App):
    """Lance Code RAG TUI application with conversational interface."""

    TITLE = "Lance Code RAG"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("f1", "help", "Help"),
    ]

    # Reactive state
    is_initialized: reactive[bool] = reactive(False)
    is_indexing: reactive[bool] = reactive(False)

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        self.project_root = project_root or Path.cwd()
        self._search_engine: SearchEngine | None = None
        self._config: LCRConfig | None = None
        self._manifest: Manifest | None = None
        # Track Ctrl+C timing for two-stage quit
        self._ctrl_c_time: float = 0.0
        self._ctrl_c_timer: object | None = None  # Timer to reset status message

    @property
    def search_engine(self) -> SearchEngine:
        """Lazy-load search engine."""
        if self._search_engine is None:
            self._search_engine = SearchEngine(self.project_root)
        return self._search_engine

    def compose(self) -> ComposeResult:
        """Create the simplified app layout."""
        with Vertical(id="main"):
            yield ChatArea(project_path=self.project_root, id="chat")
            yield StatusBar(project_path=self.project_root, id="status")
            yield SearchInput(id="input")

    async def on_mount(self) -> None:
        """Handle app mount - check initialization and show welcome."""
        self._check_initialized()

        # Focus the input by default
        self.query_one("#input", SearchInput).focus()

        # Update status bar
        self._update_status_bar()

        if self.is_initialized:
            self._load_status()
            self._show_welcome()
        else:
            # Show not initialized state - prompt user to run /init
            chat = self.query_one("#chat", ChatArea)
            chat.show_welcome(is_initialized=False)

    def _check_initialized(self) -> None:
        """Check if lcr is initialized in this project."""
        lcr_dir = get_lcr_dir(self.project_root)
        self.is_initialized = lcr_dir.exists() and (lcr_dir / "config.json").exists()

    def _load_status(self) -> None:
        """Load config and manifest."""
        try:
            self._config = load_config(self.project_root)
            self._manifest = load_manifest(self.project_root)
        except Exception:
            pass

    def _update_status_bar(self) -> None:
        """Update the status bar with current state."""
        status_bar = self.query_one("#status", StatusBar)
        file_count = self._manifest.stats.total_files if self._manifest else None

        status_bar.update(
            is_initialized=self.is_initialized,
            file_count=file_count,
        )

        if not self.is_initialized:
            status_bar.set_not_initialized()
        elif self.is_indexing:
            status_bar.set_indexing()
        else:
            status_bar.set_ready()

    def _show_welcome(self) -> None:
        """Show welcome box with current status."""
        chat = self.query_one("#chat", ChatArea)
        chat.show_welcome(
            config=self._config,
            stats=self._manifest.stats if self._manifest else None,
            is_initialized=self.is_initialized,
        )

    async def _launch_init_wizard(self) -> None:
        """Launch the init wizard."""
        chat = self.query_one("#chat", ChatArea)
        chat.show_assistant_message("Project not initialized. Launching setup wizard...")

        try:
            result = await asyncio.to_thread(self._run_wizard_sync)
        except Exception as e:
            chat.show_status(f"Wizard error: {e}", success=False)
            chat.show_assistant_message("Run /init to try again.", style="dim")
            return

        if result.cancelled:
            chat.show_status("Setup cancelled", success=False)
            chat.show_assistant_message("Run /init when ready.", style="dim")
        else:
            await self._do_init(result, auto_index=True)

    def _run_wizard_sync(self) -> WizardResult:
        """Run the wizard app synchronously (for use with to_thread)."""
        try:
            app = InitWizardApp()
            result = app.run()
            return result if result else WizardResult(cancelled=True)
        except Exception as e:
            raise RuntimeError(f"Wizard failed: {e}") from e

    async def _do_init(self, result: WizardResult, auto_index: bool = False) -> None:
        """Perform initialization with wizard result."""
        chat = self.query_one("#chat", ChatArea)

        try:
            chat.show_assistant_message(
                f"Initializing with {result.provider} provider..."
            )

            # Create config
            config = LCRConfig(
                embedding_provider=result.provider,
                embedding_model=result.model,
                embedding_dimensions=result.dimensions,
            )

            # Create directories and save config
            lcr_dir = get_lcr_dir(self.project_root)
            lcr_dir.mkdir(parents=True, exist_ok=True)
            save_config(config, self.project_root)

            # Create empty manifest
            manifest = create_empty_manifest()
            save_manifest(manifest, self.project_root)

            # Update .gitignore
            self._update_gitignore()

            self.is_initialized = True
            self._config = config
            self._manifest = manifest

            chat.show_status("Initialized successfully!")
            self._update_status_bar()

            # Update welcome box
            chat.update_welcome(
                config=config,
                stats=manifest.stats,
                is_initialized=True,
            )

            if auto_index:
                chat.show_assistant_message("Starting initial indexing...")
                await self._run_indexing(force=False)

        except Exception as e:
            chat.show_status(f"Initialization failed: {e}", success=False)

    def _update_gitignore(self) -> None:
        """Add .lance-code-rag to .gitignore if not present."""
        gitignore_path = self.project_root / ".gitignore"
        entry = f"\n# Lance Code RAG\n{LCR_DIR}/\n"

        if gitignore_path.exists():
            content = gitignore_path.read_text()
            if LCR_DIR not in content:
                with open(gitignore_path, "a") as f:
                    f.write(entry)
        else:
            gitignore_path.write_text(entry.lstrip())

    @on(SearchInput.CommandSubmitted)
    async def handle_command(self, event: SearchInput.CommandSubmitted) -> None:
        """Dispatch slash commands to handlers."""
        cmd = event.command
        handlers = {
            "/init": self._handle_init,
            "/index": self._handle_index,
            "/search": self._handle_search,
            "/status": self._handle_status,
            "/clean": self._handle_clean,
            "/terminal-setup": self._handle_terminal_setup,
            "/help": self._handle_help,
            "/clear": self._handle_clear,
            "/quit": self._handle_quit,
        }

        handler = handlers.get(cmd.command)
        if handler:
            await handler(cmd.args)
        else:
            chat = self.query_one("#chat", ChatArea)
            chat.show_status(f"Unknown command: {cmd.command}", success=False)
            chat.show_assistant_message("Type /help for available commands.", style="dim")

    async def _handle_init(self, args: str) -> None:
        """Handle /init command."""
        chat = self.query_one("#chat", ChatArea)

        if self.is_initialized and "--force" not in args:
            chat.show_status("Already initialized", success=False)
            chat.show_assistant_message(
                "Use /init --force to reinitialize.", style="dim"
            )
            return

        chat.show_assistant_message("Launching setup wizard...")

        try:
            result = await asyncio.to_thread(self._run_wizard_sync)
        except Exception as e:
            chat.show_status(f"Wizard error: {e}", success=False)
            return

        if result.cancelled:
            chat.show_status("Setup cancelled", success=False)
        else:
            await self._do_init(result, auto_index=True)

    async def _handle_search(self, query: str) -> None:
        """Handle /search command."""
        chat = self.query_one("#chat", ChatArea)
        status_bar = self.query_one("#status", StatusBar)

        if not self.is_initialized:
            chat.show_status("Not initialized", success=False)
            chat.show_assistant_message("Run /init first.", style="dim")
            return

        if not query.strip():
            chat.show_status("Usage: /search <query>", success=False)
            return

        # Show user query
        chat.show_user_query(query)

        # Parse search options
        fuzzy = "--fuzzy" in query
        query = query.replace("--fuzzy", "").strip()

        bm25_weight = 0.5
        if "--bm25-weight" in query:
            parts = query.split("--bm25-weight")
            if len(parts) > 1:
                try:
                    weight_str = parts[1].split()[0]
                    bm25_weight = float(weight_str)
                    query = parts[0] + " ".join(parts[1].split()[1:])
                except (IndexError, ValueError):
                    pass
            query = query.strip()

        if not query:
            chat.show_status("Usage: /search <query>", success=False)
            return

        chat.show_assistant_message(f"Searching for: {query}...")
        status_bar.set_searching()

        try:
            results = await asyncio.to_thread(
                self.search_engine.search,
                query,
                limit=10,
                fuzzy=fuzzy,
                bm25_weight=bm25_weight,
            )
            chat.show_search_results(results)
        except SearchError as e:
            chat.show_status(f"Search error: {e}", success=False)
        except Exception as e:
            chat.show_status(f"Error: {e}", success=False)
        finally:
            status_bar.set_ready()

    async def _handle_index(self, args: str) -> None:
        """Handle /index command."""
        chat = self.query_one("#chat", ChatArea)

        if not self.is_initialized:
            chat.show_status("Not initialized", success=False)
            chat.show_assistant_message("Run /init first.", style="dim")
            return

        force = "--force" in args
        await self._run_indexing(force=force)

    async def _run_indexing(self, force: bool = False) -> None:
        """Run the indexing process."""
        chat = self.query_one("#chat", ChatArea)
        status_bar = self.query_one("#status", StatusBar)

        self.is_indexing = True
        status_bar.set_indexing(0.0)

        mode = "full re-index" if force else "incremental index"
        chat.start_indexing(f"Starting {mode}...")

        try:
            stats = await asyncio.to_thread(
                run_index,
                self.project_root,
                force=force,
                verbose=False,
                console=None,
            )

            # Show stats
            chat.finish_indexing(
                success=True,
                message=f"Indexed {stats.files_scanned} files, {stats.chunks_added} chunks",
            )

            # Reload manifest and update displays
            self._manifest = load_manifest(self.project_root)
            self._update_status_bar()

            # Update welcome box with new file count
            chat.update_welcome(
                config=self._config,
                stats=self._manifest.stats if self._manifest else None,
                is_initialized=True,
            )

        except Exception as e:
            chat.finish_indexing(success=False, message=f"Indexing failed: {e}")
        finally:
            self.is_indexing = False
            status_bar.set_ready()

    async def _handle_status(self, args: str) -> None:
        """Handle /status command."""
        chat = self.query_one("#chat", ChatArea)

        if not self.is_initialized:
            chat.show_status("Not initialized", success=False)
            chat.show_assistant_message("Run /init to set up.", style="dim")
            return

        # Build status table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        if self._config:
            table.add_row("Provider", self._config.embedding_provider)
            table.add_row("Model", self._config.embedding_model)
            table.add_row("Dimensions", str(self._config.embedding_dimensions))

        if self._manifest:
            table.add_row("Files", str(self._manifest.stats.total_files))
            table.add_row("Chunks", str(self._manifest.stats.total_chunks))
            table.add_row("Updated", self._manifest.updated_at.strftime("%Y-%m-%d %H:%M"))

        table.add_row("Status", "[green]Ready[/green]")

        from rich.panel import Panel
        from textual.widgets import Static

        chat.mount(Static(Panel(table, title="Index Status", border_style="green")))
        chat.scroll_end()

    async def _handle_clean(self, args: str) -> None:
        """Handle /clean command."""
        chat = self.query_one("#chat", ChatArea)

        if not self.is_initialized:
            chat.show_status("Nothing to clean - not initialized", success=False)
            return

        if "--confirm" not in args:
            chat.show_status("This will remove all index data", success=False)
            chat.show_assistant_message(
                "Run /clean --confirm to proceed.", style="dim"
            )
            return

        try:
            lcr_dir = get_lcr_dir(self.project_root)
            shutil.rmtree(lcr_dir)
            self.is_initialized = False
            self._config = None
            self._manifest = None
            self._search_engine = None

            chat.show_status("Cleaned successfully!")
            self._update_status_bar()

        except Exception as e:
            chat.show_status(f"Clean failed: {e}", success=False)

    async def _handle_terminal_setup(self, args: str) -> None:
        """Handle /terminal-setup command - configure VS Code for Shift+Enter."""
        import json
        import os

        chat = self.query_one("#chat", ChatArea)

        # Check if running in VS Code
        is_vscode = os.environ.get("TERM_PROGRAM") == "vscode"

        if not is_vscode:
            chat.show_status("Not running in VS Code terminal", success=False)
            chat.show_assistant_message(
                "This command configures VS Code for Shift+Enter. "
                "In other terminals, use Alt+Enter or Ctrl+J for newlines.",
                style="dim",
            )
            return

        # Find VS Code keybindings.json
        import sys
        if sys.platform == "darwin":
            keybindings_path = Path.home() / "Library/Application Support/Code/User/keybindings.json"
        elif sys.platform == "win32":
            keybindings_path = Path(os.environ.get("APPDATA", "")) / "Code/User/keybindings.json"
        else:  # Linux
            keybindings_path = Path.home() / ".config/Code/User/keybindings.json"

        # The keybinding we want to add
        new_keybinding = {
            "key": "shift+enter",
            "command": "workbench.action.terminal.sendSequence",
            "args": {"text": "\u001b\r"},
            "when": "terminalFocus",
        }

        try:
            # Read existing keybindings
            if keybindings_path.exists():
                content = keybindings_path.read_text()
                # Handle empty file or just comments
                if content.strip() and not content.strip().startswith("//"):
                    keybindings = json.loads(content)
                else:
                    keybindings = []
            else:
                keybindings_path.parent.mkdir(parents=True, exist_ok=True)
                keybindings = []

            # Check if already configured
            already_configured = any(
                kb.get("key") == "shift+enter"
                and kb.get("command") == "workbench.action.terminal.sendSequence"
                and kb.get("when") == "terminalFocus"
                for kb in keybindings
            )

            if already_configured:
                chat.show_status("VS Code already configured for Shift+Enter!", success=True)
                chat.show_assistant_message(
                    "Restart VS Code terminal if Shift+Enter isn't working.",
                    style="dim",
                )
                return

            # Add the new keybinding
            keybindings.append(new_keybinding)

            # Write back
            keybindings_path.write_text(json.dumps(keybindings, indent=2) + "\n")

            chat.show_status("VS Code configured for Shift+Enter!", success=True)
            chat.show_assistant_message(
                f"Added keybinding to {keybindings_path}",
                style="dim",
            )
            chat.show_assistant_message(
                "Restart the VS Code terminal for changes to take effect.",
                style="yellow",
            )

        except PermissionError:
            chat.show_status("Permission denied", success=False)
            chat.show_assistant_message(
                f"Cannot write to {keybindings_path}",
                style="dim",
            )
        except json.JSONDecodeError as e:
            chat.show_status("Invalid keybindings.json", success=False)
            chat.show_assistant_message(
                f"Parse error: {e}. Please fix the file manually.",
                style="dim",
            )

    async def _handle_help(self, args: str) -> None:
        """Handle /help command."""
        chat = self.query_one("#chat", ChatArea)
        chat.show_help()

    async def _handle_clear(self, args: str) -> None:
        """Handle /clear command."""
        chat = self.query_one("#chat", ChatArea)
        chat.clear()
        self._show_welcome()

    async def _handle_quit(self, args: str) -> None:
        """Handle /quit command."""
        self.exit()

    def action_interrupt(self) -> None:
        """Handle Ctrl+C: clear input first, quit on second press within 2 seconds."""
        input_widget = self.query_one("#input", SearchInput)
        status_bar = self.query_one("#status", StatusBar)
        current_time = time.monotonic()

        # Cancel any existing timer
        if self._ctrl_c_timer is not None:
            self._ctrl_c_timer.stop()
            self._ctrl_c_timer = None

        # If there's text in the input, clear it
        if input_widget.text.strip():
            input_widget.clear()
            self._ctrl_c_time = current_time
            status_bar.set_status("Input cleared. Press Ctrl+C again to quit.")
            self._ctrl_c_timer = self.set_timer(2.0, self._reset_ctrl_c_status)
            return

        # If within 2 seconds of last Ctrl+C, quit
        if current_time - self._ctrl_c_time < 2.0:
            self.exit()
            return

        # First Ctrl+C with empty input: show message and record time
        self._ctrl_c_time = current_time
        status_bar.set_status("Press Ctrl+C again to quit.")
        self._ctrl_c_timer = self.set_timer(2.0, self._reset_ctrl_c_status)

    def _reset_ctrl_c_status(self) -> None:
        """Reset status bar after Ctrl+C timeout."""
        self._ctrl_c_timer = None
        self._ctrl_c_time = 0.0  # Reset time so next Ctrl+C starts fresh
        self._update_status_bar()  # Restore normal status

    def action_quit(self) -> None:
        """Quit the application (used by /quit command)."""
        self.exit()

    def action_clear(self) -> None:
        """Clear the output."""
        chat = self.query_one("#chat", ChatArea)
        chat.clear()
        self._show_welcome()

    def action_help(self) -> None:
        """Show help."""
        chat = self.query_one("#chat", ChatArea)
        chat.show_help()


def run_app(project_root: Path | None = None) -> None:
    """Run the TUI application."""
    app = LCRApp(project_root)
    app.run()
