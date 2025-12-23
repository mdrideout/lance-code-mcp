# AGENTS.md - LLM Context for Textual TUI Development

> **Purpose**: Essential context for LLMs (Claude, etc.) starting fresh sessions on this repository. Optimized for building clean Textual TUI features quickly.

---

## Project Overview

**lance-code-rag**: Code indexing + semantic search tool with:
- **TUI**: Chat-style terminal interface (Textual) inspired by Mistral Vibe
- **MCP Server**: Model Context Protocol integration for AI assistants
- **Search**: Hybrid vector + BM25 + fuzzy search via LanceDB

**Tech Stack**: Python 3.12+, Textual, LanceDB, FastEmbed, FastMCP

---

## UI Pattern: Bottom App Swapping (Mistral Vibe Style)

We use **inline widget swapping** instead of modal screens. This keeps the chat context visible while presenting selection prompts.

### How It Works

1. **State Tracking**: `BottomApp` enum tracks what's in the input area (Input or Selector)
2. **Widget Swapping**: Remove current widget, mount new one
3. **Message Communication**: Widgets post messages when done, parent handles them
4. **Focus Management**: `can_focus=True`, `on_blur()` recaptures focus

```python
# Switch from input to inline selector
async def _switch_to_selector(self, title, options):
    # Remove search input
    search_input = self.query_one("#input", SearchInput)
    await search_input.remove()

    # Mount selector
    selector = InlineSelector(title, options, id="selector")
    await self.mount(selector)
    self._current_bottom_app = BottomApp.Selector
    self.call_after_refresh(selector.focus)

# Handle selection via message
@on(InlineSelector.OptionSelected)
async def _on_option_selected(self, event):
    # Process selection, then restore input
    await self._switch_to_input()
```

### Multi-Step Flows

For wizards like `/init` that need multiple selections:

```python
# Track flow state
self._flow_state = {"flow": "init", "step": "provider"}

# Each selection advances the flow
async def _handle_init_selection(self, value):
    step = self._flow_state.get("step")

    if step == "provider":
        # Store selection, show next selector
        self._flow_state["provider"] = value
        self._flow_state["step"] = "model"
        await self._switch_to_selector("Select model:", model_options)

    elif step == "model":
        # All done - restore input and complete
        await self._switch_to_input()
        await self._complete_init(...)
        self._flow_state = {}
```

---

## CRITICAL GOTCHAS

### 1. Testing Gotcha

- `run_test()` with Pilot is **headless simulation** - may not catch real terminal issues
- Always test with actual terminal (`uv run lcr`) when debugging keyboard/focus problems

### 2. Widget Swapping Must Await remove_children()

**Problem**: `DuplicateIds` error when swapping widgets.

**Cause**: `remove_children()` is async - if not awaited, the old widget still exists when mounting the new one.

```python
# WRONG - causes DuplicateIds
input_area.remove_children()  # Not awaited!
await input_area.mount(new_widget)

# CORRECT
await input_area.remove_children()
await input_area.mount(new_widget)
```

### 3. Textual Workers for Blocking I/O

**Problem**: Long-running blocking operations freeze the UI.

**Solution**: Use `@work(thread=True)` decorator for blocking functions.

#### CRITICAL: Correct Worker Pattern

```python
from textual import work
from textual.worker import get_current_worker

# For BLOCKING (sync) functions - use thread=True
@work(exclusive=True, thread=True, group="indexing")
def do_blocking_work(self, param: str) -> None:
    """Runs in a thread. Use call_from_thread() for UI updates."""
    worker = get_current_worker()

    # Do blocking work
    result = some_blocking_operation()

    # Update UI safely from thread
    if not worker.is_cancelled:
        self.call_from_thread(self._on_work_complete, result)

# For ASYNC functions - no thread=True
@work(exclusive=True)
async def do_async_work(self) -> None:
    """Runs as async task."""
    result = await some_async_operation()
    self.update_ui(result)  # Can update directly
```

#### WRONG Patterns (Common Mistakes)

```python
# WRONG: Don't wrap @work-decorated methods in run_worker()
@work(thread=True)
def my_worker(self):
    pass

# BAD - double-wrapping!
self.run_worker(self.my_worker())

# GOOD - just call directly, decorator handles it
self.my_worker()
```

```python
# WRONG: Don't use asyncio.to_thread inside @on handlers
@on(SomeMessage)
async def handler(self, event):
    # This can freeze the UI!
    await asyncio.to_thread(blocking_func)

# GOOD: Use @work(thread=True) method instead
@on(SomeMessage)
async def handler(self, event):
    self._do_blocking_work()  # @work decorated

@work(thread=True)
def _do_blocking_work(self):
    blocking_func()
```

```python
# WRONG: Import from textual.work
from textual.work import work  # ModuleNotFoundError!

# CORRECT: Import from textual
from textual import work
```

#### UI Updates from Thread Workers

```python
@work(thread=True)
def _run_indexing(self, force: bool) -> None:
    worker = get_current_worker()

    # Signal start
    self.call_from_thread(self._on_indexing_started)

    try:
        result = run_blocking_index()
        if not worker.is_cancelled:
            self.call_from_thread(self._on_indexing_complete, result)
    except Exception as e:
        if not worker.is_cancelled:
            self.call_from_thread(self._on_indexing_error, str(e))

def _on_indexing_started(self) -> None:
    """Called from thread - updates UI."""
    self.query_one("#status").set_indexing()

def _on_indexing_complete(self, result) -> None:
    """Called from thread - updates UI."""
    self.query_one("#chat").show_result(result)
```

### 4. Rich Console Conflicts with Textual

**Problem**: Rich Console/Progress in background threads can interfere with Textual's terminal control.

**Solution**: Create a null console for background operations:

```python
from rich.console import Console
null_console = Console(force_terminal=False, no_color=True, quiet=True)
result = run_index(console=null_console)
```

---

## Pattern Cheat Sheet

### DO:
- Use inline widget swapping (remove + mount) for selection prompts
- Use `call_after_refresh(widget.focus)` after mounting
- Use `can_focus=True` + `can_focus_children=False` on interactive widgets
- Use `on_blur()` to recapture focus during selection
- Use `post_message()` for widget → parent communication
- Use declarative `BINDINGS` with `action_*` methods
- Yield widgets directly at Screen level (no wrapper container)
- Track multi-step flow state in a dict
- Use `@work(thread=True)` for blocking I/O operations
- Use `call_from_thread()` to update UI from thread workers
- Always `await` `remove_children()` before mounting new widgets
- Import `work` from `textual`, not `textual.work`

### DON'T:
- Don't use ModalScreen for selection prompts (use inline widgets)
- Don't toggle visibility (`display=False`) - remove and mount widgets instead
- Don't nest focusable widgets without `can_focus_children=False`
- Don't rely solely on `run_test()` - test in real terminal for input issues
- Don't wrap `@work`-decorated methods in `run_worker()` - just call them directly
- Don't use `asyncio.to_thread()` inside `@on` handlers - use `@work(thread=True)` instead
- Don't use Rich Console/Progress in threads without `force_terminal=False`

---

## Architecture Quick Reference

```
src/lance_code_rag/tui/
├── app.py              # Main LCRApp - bottom app swapping, flow handlers
├── app.tcss            # Textual CSS styles
└── widgets/
    ├── inline_selector.py  # Inline selection widget (replaces input)
    ├── chat_area.py        # Scrollable message area
    ├── search_input.py     # Command input with slash commands
    ├── status_bar.py       # Bottom status bar
    ├── welcome_box.py      # ASCII art welcome banner
    └── messages.py         # Message display widgets
```

**Key Files to Study:**
- `app.py:150` - `_switch_to_selector()` and `_switch_to_input()` methods
- `app.py:209` - `_on_option_selected()` message handler
- `app.py:284` - `_handle_init()` starting the init flow
- `inline_selector.py` - Complete inline selection widget pattern

---

## Reference Repositories

### Mistral Vibe CLI (Primary Inspiration)
- **URL**: https://github.com/mistralai/mistral-vibe
- **Key files**:
  - `vibe/cli/textual_ui/app.py` - Main app, bottom app swapping
  - `vibe/cli/textual_ui/widgets/config_app.py` - Inline config widget
  - `vibe/cli/textual_ui/widgets/approval_app.py` - Inline approval widget
- **Patterns**: Bottom app swapping, inline prompts, focus management, message-based communication
- **Study this first** for inline chat UI patterns

### Elia (Chat TUI Reference)
- **URL**: https://github.com/darrenburns/elia
- **What**: Keyboard-centric terminal LLM chat interface
- **Useful for**: Chat UI patterns, conversation storage, multi-model support
- Good example of polished chat-style TUI

---

## Reference Documentation

### Textual Docs (Critical Pages)
- **Input/Focus**: https://textual.textualize.io/guide/input/
- **Actions/Bindings**: https://textual.textualize.io/guide/actions/
- **Widgets**: https://textual.textualize.io/guide/widgets/
- **Messages**: https://textual.textualize.io/guide/events/
- **Workers**: https://textual.textualize.io/guide/workers/ (if you need async tasks)

---

## Existing Documentation

See `MISTRAL_ARCHITECTURE.md` for detailed Mistral Vibe analysis (800+ lines) covering:
- Widget hierarchy and composition
- Bottom app pattern implementation
- Focus management strategies
- Message-based communication patterns
- CSS styling approach

---

## Quick Patterns

### InlineSelector Widget
```python
class InlineSelector(Vertical):
    can_focus = True
    can_focus_children = False

    BINDINGS = [
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("enter", "select", show=False),
        Binding("escape", "cancel", show=False),
    ]

    class OptionSelected(Message):
        def __init__(self, value: str, label: str):
            self.value = value
            self.label = label
            super().__init__()

    class SelectionCancelled(Message):
        pass

    def on_mount(self):
        self._update_display()
        self.focus()

    def on_blur(self, event):
        # Recapture focus to prevent escape
        self.call_after_refresh(self.focus)

    def action_select(self):
        value, label = self._options[self._selected_index]
        self.post_message(self.OptionSelected(value, label))

    def action_cancel(self):
        self.post_message(self.SelectionCancelled())
```

### Flow State Machine
```python
# Start flow
self._flow_state = {"flow": "init", "step": "provider"}
await self._switch_to_selector("Select provider:", options)

# Handle message
@on(InlineSelector.OptionSelected)
async def _on_option_selected(self, event):
    flow = self._flow_state.get("flow")
    if flow == "init":
        await self._handle_init_selection(event.value)

# On cancel, restore input
@on(InlineSelector.SelectionCancelled)
async def _on_cancelled(self, event):
    await self._switch_to_input()
    self._flow_state = {}
```
