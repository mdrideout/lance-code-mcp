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

## CRITICAL GOTCHAS

### 1. The @work Decorator Issue

**Problem**: `await` inside `@on` event handlers blocks the Textual event loop.

**Symptom**: Modal screens/prompts appear but keyboard input never arrives. App appears frozen.

**Solution**: Use `@work(exclusive=True)` decorator on handlers that await user input.

```python
# BAD - blocks event loop, keyboard input never reaches modal
@on(SearchInput.CommandSubmitted)
async def handle_command(self, event):
    result = await self._prompt_selection(...)  # BLOCKS!

# GOOD - @work runs in separate task, event loop stays responsive
@on(SearchInput.CommandSubmitted)
def handle_command(self, event):
    self._handle_init_worker(event.args)  # Calls @work method

@work(exclusive=True)
async def _handle_init_worker(self, args):
    result = await self._prompt_selection(...)  # Works!
```

### 2. Testing Gotcha

- `run_test()` with Pilot is **headless simulation** - may not catch real terminal issues
- Always test with actual terminal (`uv run lcr`) when debugging keyboard/focus problems

---

## UI Style Preference: Inline Over Modal

**PREFER inline chat interfaces** that keep the conversation flow visible:
- Mistral Vibe uses "bottom app swapping" - widgets mounted inline, not modal overlays
- User stays in chat context, sees previous messages while making selections
- See `MISTRAL_ARCHITECTURE.md` → "Bottom App Pattern" for the full pattern

**When ModalScreen is acceptable:**
- When inline focus management becomes unreliable
- For truly modal confirmations (destructive actions)

**Current State & Future Work:**
- `SelectionScreen` uses ModalScreen due to inline focus issues we hit
- **TODO**: Investigate if @work + proper focus management enables inline prompts
- **Goal**: Refactor to inline "bottom app swapping" pattern like Mistral Vibe

**Inline Widget Pattern (Mistral Vibe Style):**
```python
# Swap widgets in a container - NOT overlay modals
async def _switch_to_selection(self):
    container = self.query_one("#bottom-app-container")
    await self.query_one("#input").remove()      # Remove old widget
    await container.mount(SelectionWidget(...))  # Mount new widget
    self.call_after_refresh(new_widget.focus)    # Focus after refresh
```

---

## Pattern Cheat Sheet

### DO:
- **Prefer inline prompts** over modal screens when focus management works
- Use `@work(exclusive=True)` for handlers that await user input
- Use widget replacement pattern (remove + mount) not visibility toggle
- Use `call_after_refresh(widget.focus)` after mounting
- Use declarative `BINDINGS` with `action_*` methods
- Yield widgets directly at Screen level (no wrapper container)
- Use `can_focus=True` + `can_focus_children=False` on interactive containers
- Use `on_blur()` to recapture focus if needed

### DON'T:
- Don't `await` inside `@on` decorated event handlers (blocks keyboard input)
- Don't toggle visibility (`display=False`) - remove and mount widgets instead
- Don't nest focusable widgets without `can_focus_children=False`
- Don't rely solely on `run_test()` - test in real terminal for input issues

---

## Architecture Quick Reference

```
src/lance_code_rag/tui/
├── app.py              # Main LCRApp - command handlers, @work patterns
├── app.tcss            # Textual CSS styles
├── screens/
│   └── selection_screen.py   # ModalScreen for selection prompts
└── widgets/
    ├── chat_area.py    # Scrollable message area
    ├── search_input.py # Command input with slash commands
    ├── status_bar.py   # Bottom status bar
    ├── welcome_box.py  # ASCII art welcome banner
    └── messages.py     # Message display widgets
```

**Key Files to Study:**
- `app.py:188` - `handle_command()` showing @work pattern
- `app.py:226` - `_handle_init_worker()` with @work decorator
- `app.py:136` - `_prompt_selection()` with Future/callback pattern

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
- **Workers**: https://textual.textualize.io/guide/workers/ (CRITICAL for async handlers)
- **Screens**: https://textual.textualize.io/guide/screens/
- **Input/Focus**: https://textual.textualize.io/guide/input/
- **Actions/Bindings**: https://textual.textualize.io/guide/actions/
- **Widgets**: https://textual.textualize.io/guide/widgets/

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

### ModalScreen with Future/Callback
```python
async def _prompt_selection(self, title, options):
    future = asyncio.Future()

    def on_dismiss(result):
        future.set_result(result)

    screen = SelectionScreen(title, options)
    self.push_screen(screen, on_dismiss)

    return await future  # Only works inside @work method!
```

### Interactive Widget with Focus
```python
class SelectionWidget(Container):
    can_focus = True
    can_focus_children = False

    BINDINGS = [
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("enter", "select", show=False),
        Binding("escape", "cancel", show=False),
    ]

    def on_mount(self):
        self._update_display()
        self.focus()

    def on_blur(self, event):
        # Recapture focus to prevent escape
        self.call_after_refresh(self.focus)

    def action_select(self):
        self.post_message(self.Selected(self.value))
```
