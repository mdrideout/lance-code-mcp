"""Main TUI application for Lance Code RAG - Mistral Vibe style."""

import asyncio
import json
import shutil
import time
from enum import StrEnum, auto
from pathlib import Path

from rich.table import Table
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive

from .. import LCR_DIR
from ..config import LCRConfig, get_lcr_dir, load_config, save_config
from ..indexer import run_index
from ..manifest import Manifest, create_empty_manifest, load_manifest, save_manifest
from ..search import SearchEngine, SearchError
from .widgets import ChatArea, InlineSelector, SearchInput, StatusBar


class BottomApp(StrEnum):
    """Which widget is currently in the bottom input area."""

    Input = auto()
    Selector = auto()


# Embedding provider options
PROVIDERS = [
    ("local", "Local (FastEmbed) - runs on your machine"),
    ("openai", "OpenAI (coming soon)"),
    ("gemini", "Gemini (coming soon)"),
]

# Local embedding model options: (id, display, model_name, dimensions)
LOCAL_MODELS = [
    ("bge-small", "bge-small (~33MB) - fastest", "BAAI/bge-small-en-v1.5", 384),
    ("bge-base", "bge-base (~130MB) - recommended", "BAAI/bge-base-en-v1.5", 768),
    ("bge-large", "bge-large (~330MB) - highest quality", "BAAI/bge-large-en-v1.5", 1024),
]


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

        # Bottom app swapping state (Mistral Vibe pattern)
        self._current_bottom_app = BottomApp.Input

        # Multi-step flow state (for /init, /remove)
        # Keys: "flow" (e.g., "init", "remove"), plus flow-specific state
        self._flow_state: dict = {}

    @property
    def search_engine(self) -> SearchEngine:
        """Lazy-load search engine."""
        if self._search_engine is None:
            self._search_engine = SearchEngine(self.project_root)
        return self._search_engine

    def compose(self) -> ComposeResult:
        """Create app layout with widgets directly at Screen level."""
        yield ChatArea(project_path=self.project_root, id="chat")
        yield StatusBar(project_path=self.project_root, id="status")
        yield SearchInput(id="input")

    async def on_mount(self) -> None:
        """Handle app mount - check initialization and show welcome."""
        self._check_initialized()

        # Focus the search input
        search_input = self.query_one("#input", SearchInput)
        self.call_after_refresh(search_input.focus)

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

    # ─────────────────────────────────────────────────────────────────────
    # Bottom App Swapping (Mistral Vibe pattern)
    # ─────────────────────────────────────────────────────────────────────

    async def _switch_to_selector(
        self,
        title: str,
        options: list[tuple[str, str]],
        default_index: int = 0,
    ) -> None:
        """Switch from input to inline selector.

        The selector replaces the search input at the bottom of the screen.
        When the user makes a selection or cancels, InlineSelector posts
        a message which we handle to restore the input and continue the flow.
        """
        if self._current_bottom_app == BottomApp.Selector:
            # Already showing a selector - remove it first
            try:
                old_selector = self.query_one("#selector", InlineSelector)
                await old_selector.remove()
            except Exception:
                pass

        # Remove search input
        try:
            search_input = self.query_one("#input", SearchInput)
            await search_input.remove()
        except Exception:
            pass

        # Mount selector
        selector = InlineSelector(title, options, default_index, id="selector")
        await self.mount(selector)
        self._current_bottom_app = BottomApp.Selector
        self.call_after_refresh(selector.focus)

    async def _switch_to_input(self) -> None:
        """Switch from selector back to search input."""
        if self._current_bottom_app == BottomApp.Input:
            return

        # Remove selector
        try:
            selector = self.query_one("#selector", InlineSelector)
            await selector.remove()
        except Exception:
            pass

        # Mount search input
        search_input = SearchInput(id="input")
        await self.mount(search_input)
        self._current_bottom_app = BottomApp.Input
        self.call_after_refresh(search_input.focus)

    # ─────────────────────────────────────────────────────────────────────
    # InlineSelector Message Handlers
    # ─────────────────────────────────────────────────────────────────────

    @on(InlineSelector.OptionSelected)
    async def _on_option_selected(self, event: InlineSelector.OptionSelected) -> None:
        """Handle option selection from inline selector."""
        flow = self._flow_state.get("flow")

        if flow == "init":
            await self._handle_init_selection(event.value)
        elif flow == "remove":
            await self._handle_remove_selection(event.value)
        else:
            # Unknown flow - just restore input
            await self._switch_to_input()
            self._flow_state = {}

    @on(InlineSelector.SelectionCancelled)
    async def _on_selection_cancelled(
        self, event: InlineSelector.SelectionCancelled
    ) -> None:
        """Handle selection cancellation."""
        chat = self.query_one("#chat", ChatArea)
        flow = self._flow_state.get("flow")

        if flow:
            chat.show_status(f"{flow.title()} cancelled", success=False)

        await self._switch_to_input()
        self._flow_state = {}

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
    def handle_command(self, event: SearchInput.CommandSubmitted) -> None:
        """Dispatch slash commands to handlers.

        Commands that show inline selectors use the bottom app swapping pattern.
        Other commands are simple async handlers.
        """
        cmd = event.command

        # All commands are now async handlers (no @work needed with inline pattern)
        async_handlers = {
            "/init": self._handle_init,
            "/remove": self._handle_remove,
            "/index": self._handle_index,
            "/search": self._handle_search,
            "/status": self._handle_status,
            "/clean": self._handle_clean,
            "/terminal-setup": self._handle_terminal_setup,
            "/help": self._handle_help,
            "/clear": self._handle_clear,
            "/quit": self._handle_quit,
        }

        if cmd.command in async_handlers:
            self.run_worker(async_handlers[cmd.command](cmd.args))
        else:
            chat = self.query_one("#chat", ChatArea)
            chat.show_status(f"Unknown command: {cmd.command}", success=False)
            chat.show_assistant_message("Type /help for available commands.", style="dim")

    # ─────────────────────────────────────────────────────────────────────
    # /init Flow (multi-step inline selection)
    # ─────────────────────────────────────────────────────────────────────

    async def _handle_init(self, args: str) -> None:
        """Start the /init flow - shows first inline selector."""
        chat = self.query_one("#chat", ChatArea)

        if self.is_initialized and "--force" not in args:
            chat.show_status("Already initialized", success=False)
            chat.show_assistant_message("Use /init --force to reinitialize.", style="dim")
            return

        chat.show_assistant_message("Initializing lance-code-rag...")

        # Start init flow - step 1: select provider
        self._flow_state = {"flow": "init", "step": "provider"}
        await self._switch_to_selector("Select embedding provider:", PROVIDERS)

    async def _handle_init_selection(self, value: str) -> None:
        """Handle selections during the /init flow."""
        chat = self.query_one("#chat", ChatArea)
        step = self._flow_state.get("step")

        if step == "provider":
            # Provider selected
            if value != "local":
                chat.show_status(f"{value.title()} coming soon!", success=False)
                chat.show_assistant_message("Only local embeddings are available currently.")
                await self._switch_to_input()
                self._flow_state = {}
                return

            chat.show_status(f"Provider: {value}")
            self._flow_state["provider"] = value

            # Step 2: select model
            self._flow_state["step"] = "model"
            model_options = [(m[0], m[1]) for m in LOCAL_MODELS]
            await self._switch_to_selector(
                "Select embedding model:",
                model_options,
                default_index=1,  # bge-base recommended
            )

        elif step == "model":
            # Model selected - finish init
            model_id = value
            model_info = next((m for m in LOCAL_MODELS if m[0] == model_id), None)
            if not model_info:
                chat.show_status("Invalid model selection", success=False)
                await self._switch_to_input()
                self._flow_state = {}
                return

            _, _, model_name, dimensions = model_info
            chat.show_status(f"Model: {model_id}")

            # Restore input before continuing
            await self._switch_to_input()

            # Complete initialization
            await self._complete_init(
                provider=self._flow_state.get("provider", "local"),
                model_name=model_name,
                dimensions=dimensions,
            )
            self._flow_state = {}

    async def _complete_init(
        self, provider: str, model_name: str, dimensions: int
    ) -> None:
        """Complete the initialization after selections are made."""
        chat = self.query_one("#chat", ChatArea)

        try:
            chat.show_assistant_message("Creating config...")

            # Create config
            config = LCRConfig(
                embedding_provider=provider,
                embedding_model=model_name,
                embedding_dimensions=dimensions,
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

            # Update .mcp.json
            self._update_mcp_config()

            self.is_initialized = True
            self._config = config
            self._manifest = manifest

            chat.show_status("Config saved!")
            self._update_status_bar()

            # Update welcome box
            chat.update_welcome(
                config=config,
                stats=manifest.stats,
                is_initialized=True,
            )

            # Auto-index
            chat.show_assistant_message("Starting initial indexing...")
            await self._run_indexing(force=False)

        except Exception as e:
            chat.show_status(f"Initialization failed: {e}", success=False)

    def _update_mcp_config(self) -> None:
        """Add lance-code-rag to .mcp.json if not present."""
        mcp_path = self.project_root / ".mcp.json"
        config_entry = {
            "command": "lcr",
            "args": ["serve"],
            "env": {
                "LCR_ROOT": str(self.project_root),
            },
        }

        try:
            if mcp_path.exists():
                content = json.loads(mcp_path.read_text())
            else:
                content = {"mcpServers": {}}

            if "mcpServers" not in content:
                content["mcpServers"] = {}

            content["mcpServers"]["lance-code-rag"] = config_entry
            mcp_path.write_text(json.dumps(content, indent=2) + "\n")
        except Exception:
            pass  # Non-critical, don't fail init

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
            chat.show_assistant_message("Run /clean --confirm to proceed.", style="dim")
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

    # ─────────────────────────────────────────────────────────────────────
    # /remove Flow (single-step inline selection)
    # ─────────────────────────────────────────────────────────────────────

    async def _handle_remove(self, args: str) -> None:
        """Start the /remove flow - shows confirmation selector."""
        chat = self.query_one("#chat", ChatArea)

        if not self.is_initialized:
            chat.show_status("Not initialized - nothing to remove", success=False)
            return

        chat.show_assistant_message("Remove lance-code-rag from this project?")

        # Start remove flow
        self._flow_state = {"flow": "remove"}
        await self._switch_to_selector(
            "This will remove:",
            [
                ("yes", "Yes, remove completely"),
                ("no", "No, cancel"),
            ],
        )

    async def _handle_remove_selection(self, value: str) -> None:
        """Handle selection during the /remove flow."""
        chat = self.query_one("#chat", ChatArea)

        # Restore input first
        await self._switch_to_input()
        self._flow_state = {}

        if value != "yes":
            chat.show_status("Removal cancelled", success=False)
            return

        # Execute removal with progress
        try:
            # 1. Remove .lance-code-rag/ directory
            chat.show_assistant_message("Removing .lance-code-rag/ directory...")
            lcr_dir = get_lcr_dir(self.project_root)
            if lcr_dir.exists():
                shutil.rmtree(lcr_dir)
            chat.show_status("Directory removed!")

            # 2. Remove from .gitignore
            chat.show_assistant_message("Cleaning .gitignore...")
            self._remove_gitignore_entry()
            chat.show_status("Gitignore cleaned!")

            # 3. Remove from .mcp.json
            chat.show_assistant_message("Cleaning .mcp.json...")
            self._remove_mcp_config()
            chat.show_status("MCP config cleaned!")

            # Reset state
            self.is_initialized = False
            self._config = None
            self._manifest = None
            self._search_engine = None

            chat.show_status("Removal complete!", success=True)
            self._update_status_bar()

            # Show not-initialized welcome
            chat.show_welcome(is_initialized=False)

        except Exception as e:
            chat.show_status(f"Removal failed: {e}", success=False)

    def _remove_gitignore_entry(self) -> None:
        """Remove .lance-code-rag from .gitignore."""
        gitignore_path = self.project_root / ".gitignore"
        if not gitignore_path.exists():
            return

        lines = gitignore_path.read_text().splitlines(keepends=True)
        new_lines = []
        skip_next = False

        for line in lines:
            # Skip the comment and the entry
            if "# Lance Code RAG" in line:
                skip_next = True
                continue
            if skip_next and LCR_DIR in line:
                skip_next = False
                continue
            skip_next = False
            new_lines.append(line)

        # Write back, removing trailing empty lines
        content = "".join(new_lines).rstrip() + "\n" if new_lines else ""
        gitignore_path.write_text(content)

    def _remove_mcp_config(self) -> None:
        """Remove lance-code-rag from .mcp.json."""
        mcp_path = self.project_root / ".mcp.json"
        if not mcp_path.exists():
            return

        try:
            content = json.loads(mcp_path.read_text())
            if "mcpServers" in content and "lance-code-rag" in content["mcpServers"]:
                del content["mcpServers"]["lance-code-rag"]

                # If no servers left, remove the file
                if not content["mcpServers"]:
                    mcp_path.unlink()
                else:
                    mcp_path.write_text(json.dumps(content, indent=2) + "\n")
        except Exception:
            pass  # Non-critical

    async def _handle_terminal_setup(self, args: str) -> None:
        """Handle /terminal-setup command - configure VS Code for Shift+Enter."""
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
            keybindings_path = (
                Path.home() / "Library/Application Support/Code/User/keybindings.json"
            )
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
