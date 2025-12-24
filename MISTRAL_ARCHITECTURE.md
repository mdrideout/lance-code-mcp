# Mistral Vibe CLI - Textual UI Architecture Analysis

This document analyzes the Textual TUI architecture used by [Mistral Vibe CLI](https://github.com/mistralai/mistral-vibe), focusing on widget composition, focus management, keyboard navigation, and interactive wizards/prompts.

---

## Table of Contents

1. [Overall Architecture](#overall-architecture)
2. [Widget Hierarchy](#widget-hierarchy)
3. [Bottom App Pattern](#bottom-app-pattern)
4. [Focus Management Strategy](#focus-management-strategy)
5. [Interactive Widget Pattern](#interactive-widget-pattern)
6. [Message-Based Communication](#message-based-communication)
7. [Key Binding Patterns](#key-binding-patterns)
8. [CSS Styling Approach](#css-styling-approach)

---

## Overall Architecture

### App Entry Point and Terminal Takeover

Mistral Vibe's TUI takes full control of the terminal via Textual's **application mode** (alternate screen buffer):

```python
# vibe/cli/textual_ui/app.py
def run_textual_ui(config, ...):
    app = VibeApp(config, ...)
    app.run()  # Enters alternate screen mode - NO terminal scrollback
```

When `app.run()` is called (without `inline=True`), Textual:
1. Switches to the alternate screen buffer
2. Clears the visible terminal
3. Renders the TUI full-screen
4. Restores original terminal on exit

**Key insight**: Users CANNOT scroll up past the TUI because the terminal history is hidden in the main screen buffer.

### Screen-Level Widget Composition

**Critical Pattern**: Mistral Vibe composes widgets **directly at the Screen level** - there is NO outer wrapping container.

```python
# Mistral Vibe - widgets composed at Screen level
def compose(self) -> ComposeResult:
    with VerticalScroll(id="chat"):           # Direct child of Screen
        yield WelcomeBanner(self.config)
        yield Static(id="messages")

    with Horizontal(id="loading-area"):       # Direct child of Screen
        yield Static(id="loading-area-content")
        yield ModeIndicator(mode=self._current_agent_mode)

    yield Static(id="todo-area")              # Direct child of Screen

    with Static(id="bottom-app-container"):   # Direct child of Screen
        yield ChatInputContainer(...)

    with Horizontal(id="bottom-bar"):         # Direct child of Screen
        yield PathDisplay(...)
        yield Static(id="spacer")
        yield ContextProgress()
```

**Anti-pattern to avoid**:
```python
# DON'T do this - subclassing VerticalScroll or wrapping creates layout issues
class ChatArea(VerticalScroll):  # ← Don't subclass!
    ...

def compose(self) -> ComposeResult:
    with Vertical(id="main"):           # ← Extra wrapper!
        yield ChatArea(...)             # ← Subclassed widget!
        yield StatusBar(...)
        yield Container(id="bottom-app-container")
```

**Correct pattern** (matching Elia - mount directly into VerticalScroll):
```python
def compose(self) -> ComposeResult:
    # CRITICAL: can_focus=False allows mouse wheel scrolling without focus stealing
    chat = VerticalScroll(id="chat")
    chat.can_focus = False  # ← THIS IS ESSENTIAL FOR MOUSE SCROLLING
    yield chat
    yield StatusBar(...)
    yield Container(id="bottom-app-container")

# Then mount widgets directly into VerticalScroll:
chat = self.query_one("#chat", VerticalScroll)
chat.mount(widget)
chat.scroll_end()
```

**Critical Requirements for Mouse Scrolling**:
1. `can_focus = False` on VerticalScroll - allows mouse wheel events to work without focus stealing
2. Do NOT wrap widgets in a `Static` inside `VerticalScroll` - creates nested scroll areas
3. All child widgets MUST have `height: auto` in CSS - allows natural content flow
4. All child widgets MUST have `width: 100%` in CSS - fills parent container

The extra `Vertical(id="main")` wrapper can cause:
- Improper screen filling
- Potential scrollback visibility issues
- Layout complexity

### App Class Configuration

```python
class VibeApp(App):
    ENABLE_COMMAND_PALETTE = False      # No command palette
    CSS_PATH = "app.tcss"               # External stylesheet

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "clear_quit", "Quit", show=False),
        Binding("ctrl+d", "force_quit", "Quit", show=False, priority=True),
        Binding("escape", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+o", "toggle_tool", "Toggle Tool", show=False),
        Binding("ctrl+t", "toggle_todo", "Toggle Todo", show=False),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("shift+up", "scroll_chat_up", "Scroll Up", show=False, priority=True),
        Binding("shift+down", "scroll_chat_down", "Scroll Down", show=False, priority=True),
    ]
```

### Directory Structure

```
vibe/cli/textual_ui/
├── app.py              # Main VibeApp class (46KB)
├── app.tcss            # Textual CSS styling (12KB)
├── handlers/
│   └── event_handler.py    # Agent event processing
├── renderers/              # Tool-specific UI renderers
└── widgets/
    ├── approval_app.py     # Tool approval dialog
    ├── config_app.py       # Settings interface
    ├── messages.py         # Message display widgets
    ├── welcome.py          # Welcome banner
    ├── loading.py          # Loading indicators
    ├── spinner.py          # Animated spinner
    ├── status_message.py   # Status notifications
    ├── tool_widgets.py     # Tool execution UI
    └── chat_input/
        ├── container.py    # Input container wrapper
        ├── body.py         # Input body with prompt
        ├── text_area.py    # Custom TextArea
        ├── completion_manager.py
        └── completion_popup.py
```

### Core Principle: Widget Replacement

Mistral Vibe uses a **widget replacement pattern** rather than widget overlay/visibility toggling. When switching between different UI modes (chat input, configuration, approval), the old widget is **removed from the DOM** and a new widget is **mounted in its place**.

---

## Widget Hierarchy

### Main App Layout

All widgets are **direct children of Screen** (no outer wrapper):

```
Screen (implicit, managed by Textual)
├── VerticalScroll (id="chat")          # Scrollable chat area
│   ├── WelcomeBanner
│   └── Static (id="messages")          # Dynamic content
├── Horizontal (id="loading-area")
│   ├── Static (id="loading-area-content")
│   └── ModeIndicator
├── Static (id="todo-area")
├── Static (id="bottom-app-container")  # SWAPPABLE AREA
│   └── ChatInputContainer  OR  ConfigApp  OR  ApprovalApp  OR  InlinePrompt
└── Horizontal (id="bottom-bar")
    ├── PathDisplay
    ├── Static (id="spacer")
    └── ContextProgress
```

### Key Insight: The Bottom App Container

The `#bottom-app-container` is a **swap zone** where different interactive widgets are mounted/unmounted based on context:

- **ChatInputContainer** - Default text input for chatting
- **ConfigApp** - Settings/configuration panel
- **ApprovalApp** - Tool execution approval dialog

Only ONE of these exists in the DOM at any time.

---

## Bottom App Pattern

### State Tracking with Enum

```python
class BottomApp(StrEnum):
    Approval = auto()
    Config = auto()
    Input = auto()
```

The app maintains `self._current_bottom_app` to track which widget is active.

### Switching Between Bottom Apps

#### Switch to Config App

```python
async def _switch_to_config_app(self) -> None:
    if self._current_bottom_app == BottomApp.Config:
        return

    bottom_container = self.query_one("#bottom-app-container")

    # 1. Remove existing ChatInputContainer
    try:
        chat_input_container = self.query_one(ChatInputContainer)
        await chat_input_container.remove()
    except Exception:
        pass

    # 2. Hide mode indicator (only shown for Input)
    if self._mode_indicator:
        self._mode_indicator.display = False

    # 3. Create and mount ConfigApp
    config_app = ConfigApp(self.config)
    await bottom_container.mount(config_app)

    # 4. Update state
    self._current_bottom_app = BottomApp.Config

    # 5. Focus AFTER refresh cycle
    self.call_after_refresh(config_app.focus)
```

#### Switch to Approval App

```python
async def _switch_to_approval_app(self, tool_name: str, tool_args: dict) -> None:
    bottom_container = self.query_one("#bottom-app-container")

    # Remove ChatInputContainer
    try:
        chat_input_container = self.query_one(ChatInputContainer)
        await chat_input_container.remove()
    except Exception:
        pass

    if self._mode_indicator:
        self._mode_indicator.display = False

    # Mount ApprovalApp
    approval_app = ApprovalApp(
        tool_name=tool_name,
        tool_args=tool_args,
        workdir=str(self.config.effective_workdir),
        config=self.config,
    )
    await bottom_container.mount(approval_app)
    self._current_bottom_app = BottomApp.Approval

    # Focus and scroll
    self.call_after_refresh(approval_app.focus)
    self.call_after_refresh(self._scroll_to_bottom)
```

#### Switch Back to Input App

```python
async def _switch_to_input_app(self) -> None:
    bottom_container = self.query_one("#bottom-app-container")

    # Remove ConfigApp if present
    try:
        config_app = self.query_one("#config-app")
        await config_app.remove()
    except Exception:
        pass

    # Remove ApprovalApp if present
    try:
        approval_app = self.query_one("#approval-app")
        await approval_app.remove()
    except Exception:
        pass

    # Restore mode indicator
    if self._mode_indicator:
        self._mode_indicator.display = True

    # Check if ChatInputContainer already exists (reuse it)
    try:
        chat_input_container = self.query_one(ChatInputContainer)
        self._chat_input_container = chat_input_container
        self._current_bottom_app = BottomApp.Input
        self.call_after_refresh(chat_input_container.focus_input)
        return
    except Exception:
        pass

    # Create new ChatInputContainer
    chat_input_container = ChatInputContainer(
        history_file=self.history_file,
        command_registry=self.commands,
        id="input-container",
        safety=self._current_agent_mode.safety,
    )
    await bottom_container.mount(chat_input_container)
    self._chat_input_container = chat_input_container
    self._current_bottom_app = BottomApp.Input

    self.call_after_refresh(chat_input_container.focus_input)
```

### Focus Router

```python
def _focus_current_bottom_app(self) -> None:
    try:
        match self._current_bottom_app:
            case BottomApp.Input:
                self.query_one(ChatInputContainer).focus_input()
            case BottomApp.Config:
                self.query_one(ConfigApp).focus()
            case BottomApp.Approval:
                self.query_one(ApprovalApp).focus()
            case app:
                assert_never(app)
    except Exception:
        pass
```

---

## Focus Management Strategy

### The Core Pattern

Mistral Vibe uses three key techniques for focus management:

1. **`can_focus = True` + `can_focus_children = False`** on interactive containers
2. **`on_blur()` handler** that recaptures focus
3. **`call_after_refresh(widget.focus)`** after mounting

### ConfigApp Focus Pattern

```python
class ConfigApp(Container):
    can_focus = True
    can_focus_children = False  # Prevent children from stealing focus

    def on_mount(self) -> None:
        self._update_display()
        self.focus()

    def on_blur(self, event: events.Blur) -> None:
        # Automatically recapture focus when blurred
        self.call_after_refresh(self.focus)
```

### ApprovalApp Focus Pattern

```python
class ApprovalApp(Container):
    can_focus = True
    can_focus_children = False

    # on_blur automatically refocuses
    def on_blur(self, event: events.Blur) -> None:
        self.call_after_refresh(self.focus)
```

### ChatTextArea Focus Pattern (with App Focus Tracking)

```python
class ChatTextArea(TextArea):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._app_has_focus: bool = True  # Track if app window has focus

    def on_blur(self, event: events.Blur) -> None:
        # Only refocus if the app still has focus
        # (don't refocus if user switched to another application)
        if self._app_has_focus:
            self.call_after_refresh(self.focus)

    def set_app_focus(self, has_focus: bool) -> None:
        """Called when app gains/loses window focus."""
        self._app_has_focus = has_focus
        self.cursor_blink = has_focus
        if has_focus and not self.has_focus:
            self.call_after_refresh(self.focus)
```

### Focus Delegation Chain

```
ChatInputContainer.focus_input()
    └── ChatInputBody.focus_input()
            └── ChatTextArea.focus()
```

```python
# ChatInputContainer
def focus_input(self) -> None:
    if self._body:
        self._body.focus_input()

# ChatInputBody
def focus_input(self) -> None:
    if self.input_widget:
        self.input_widget.focus()
```

---

## Interactive Widget Pattern

### Anatomy of an Interactive Widget (ConfigApp)

```python
class ConfigApp(Container):
    # 1. Focus settings - widget handles its own keys
    can_focus = True
    can_focus_children = False

    # 2. Declarative key bindings
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("space", "toggle_setting", "Toggle", show=False),
        Binding("enter", "cycle", "Next", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    # 3. Message classes for communication
    class SettingChanged(Message):
        def __init__(self, key: str, value: str) -> None:
            super().__init__()
            self.key = key
            self.value = value

    class ConfigClosed(Message):
        def __init__(self, changes: dict[str, str]) -> None:
            super().__init__()
            self.changes = changes

    def __init__(self, config: VibeConfig) -> None:
        super().__init__(id="config-app")
        self.config = config
        self.selected_index = 0
        self.changes: dict[str, str] = {}
        self.settings = [...]  # List of SettingDefinition

    # 4. Compose the UI
    def compose(self) -> ComposeResult:
        with Vertical(id="config-content"):
            yield Static("Configuration", id="config-title")
            yield Static("", id="settings-display")  # Dynamic content
            yield Static("↑↓ navigate  Space toggle  ESC close")

    # 5. Initialize on mount
    def on_mount(self) -> None:
        self._update_display()
        self.focus()

    # 6. Maintain focus
    def on_blur(self, event: events.Blur) -> None:
        self.call_after_refresh(self.focus)

    # 7. Action handlers (match BINDINGS)
    def action_move_up(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.settings)
        self._update_display()

    def action_move_down(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.settings)
        self._update_display()

    def action_toggle_setting(self) -> None:
        setting = self.settings[self.selected_index]
        # Cycle to next option
        current_idx = setting["options"].index(setting["current"])
        new_idx = (current_idx + 1) % len(setting["options"])
        setting["current"] = setting["options"][new_idx]
        self.changes[setting["key"]] = setting["current"]
        self.post_message(self.SettingChanged(setting["key"], setting["current"]))
        self._update_display()

    def action_close(self) -> None:
        self.post_message(self.ConfigClosed(changes=self.changes.copy()))

    # 8. Update visual display
    def _update_display(self) -> None:
        display = self.query_one("#settings-display", Static)
        lines = []
        for i, setting in enumerate(self.settings):
            cursor = "› " if i == self.selected_index else "  "
            lines.append(f"{cursor}{setting['label']}: {setting['current']}")
        display.update("\n".join(lines))
```

### Anatomy of ApprovalApp (Selection Widget)

```python
class ApprovalApp(Container):
    can_focus = True
    can_focus_children = False

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("escape", "reject", "Reject", show=False),
        # Quick selection shortcuts
        Binding("1", "select_1", "Yes", show=False),
        Binding("y", "select_1", "Yes", show=False),
        Binding("2", "select_2", "Always", show=False),
        Binding("3", "select_3", "No", show=False),
        Binding("n", "select_3", "No", show=False),
    ]

    class ApprovalGranted(Message):
        pass

    class ApprovalGrantedAlwaysTool(Message):
        def __init__(self, save_permanently: bool = False):
            super().__init__()
            self.save_permanently = save_permanently

    class ApprovalRejected(Message):
        pass

    def __init__(self, tool_name: str, tool_args: dict, ...):
        super().__init__(id="approval-app")
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.selected_option = 0
        self.options = [
            ("Yes", "Grant approval"),
            ("Yes, always allow", "Allow for session"),
            ("No", "Reject"),
        ]

    def compose(self) -> ComposeResult:
        yield Static(f"Approve {self.tool_name}?", id="approval-title")
        yield VerticalScroll(...)  # Tool details
        yield Static("", id="options-display")
        yield Static("↑↓ navigate  Enter select  ESC reject")

    def on_mount(self) -> None:
        self._update_display()
        self.focus()

    def on_blur(self, event: events.Blur) -> None:
        self.call_after_refresh(self.focus)

    def action_move_up(self) -> None:
        self.selected_option = (self.selected_option - 1) % len(self.options)
        self._update_display()

    def action_move_down(self) -> None:
        self.selected_option = (self.selected_option + 1) % len(self.options)
        self._update_display()

    def action_select(self) -> None:
        match self.selected_option:
            case 0:
                self.post_message(self.ApprovalGranted())
            case 1:
                self.post_message(self.ApprovalGrantedAlwaysTool())
            case 2:
                self.post_message(self.ApprovalRejected())

    def action_select_1(self) -> None:
        self.selected_option = 0
        self._update_display()
        self.action_select()

    # ... similar for select_2, select_3

    def action_reject(self) -> None:
        self.post_message(self.ApprovalRejected())
```

---

## Message-Based Communication

### Pattern: Inner Message Classes

Each interactive widget defines its own `Message` subclasses:

```python
class ConfigApp(Container):
    class SettingChanged(Message):
        def __init__(self, key: str, value: str):
            super().__init__()
            self.key = key
            self.value = value

    class ConfigClosed(Message):
        def __init__(self, changes: dict[str, str]):
            super().__init__()
            self.changes = changes
```

### Pattern: Parent Handles Messages

The parent app uses `@on()` decorators to handle child messages:

```python
class VibeApp(App):
    @on(ConfigApp.SettingChanged)
    async def on_config_setting_changed(self, event: ConfigApp.SettingChanged) -> None:
        # Apply the setting change
        if event.key == "active_model":
            self.config.active_model = event.value
        elif event.key == "textual_theme":
            self.theme = event.value

    @on(ConfigApp.ConfigClosed)
    async def on_config_closed(self, event: ConfigApp.ConfigClosed) -> None:
        # Switch back to input mode
        await self._switch_to_input_app()

    @on(ApprovalApp.ApprovalGranted)
    async def on_approval_granted(self, event: ApprovalApp.ApprovalGranted) -> None:
        # Resolve the pending approval future
        if self._approval_future:
            self._approval_future.set_result(True)
        await self._switch_to_input_app()

    @on(ApprovalApp.ApprovalRejected)
    async def on_approval_rejected(self, event: ApprovalApp.ApprovalRejected) -> None:
        if self._approval_future:
            self._approval_future.set_result(False)
        await self._switch_to_input_app()
```

### Pattern: Async Futures for Blocking Prompts

When the app needs to wait for user input (like tool approval):

```python
async def _request_approval(self, tool_name: str, tool_args: dict) -> bool:
    # Create a future to wait for
    self._approval_future = asyncio.Future()

    # Switch to approval UI
    await self._switch_to_approval_app(tool_name, tool_args)

    # Wait for user decision (message handler resolves the future)
    result = await self._approval_future

    self._approval_future = None
    return result
```

---

## Key Binding Patterns

### Declarative Bindings

```python
BINDINGS: ClassVar[list[BindingType]] = [
    Binding("up", "move_up", "Up", show=False),
    Binding("down", "move_down", "Down", show=False),
    Binding("enter", "select", "Select", show=False),
    Binding("escape", "cancel", "Cancel", show=False),
]
```

- `show=False` hides from help/footer
- `priority=True` gives precedence over parent bindings
- Multi-key: `"shift+enter,ctrl+j"` for alternatives

### Action Methods

Each binding's action maps to an `action_*` method:

```python
def action_move_up(self) -> None:
    self.selected_index = (self.selected_index - 1) % len(self.options)
    self._update_display()
```

### App-Level vs Widget-Level Bindings

**App-level** (in VibeApp):
```python
BINDINGS = [
    Binding("ctrl+c", "quit", "Quit"),
    Binding("escape", "interrupt", "Interrupt"),
    Binding("ctrl+o", "toggle_tools", "Toggle Tools"),
]
```

**Widget-level** (in ConfigApp, ApprovalApp):
```python
BINDINGS = [
    Binding("up", "move_up"),
    Binding("down", "move_down"),
]
```

Widget bindings only fire when the widget has focus.

---

## CSS Styling Approach

### Widget-Specific CSS Classes

```css
#config-app {
    height: auto;
    padding: 1 2;
    background: $surface;
    border: round $accent;
}

#approval-app {
    height: auto;
    padding: 1 2;
    background: $surface;
    border: round $warning;
}

.approval-option-yes {
    color: $success;
}

.approval-option-no {
    color: $error;
}
```

### Dynamic Class Application

```python
def _update_display(self) -> None:
    for i, option in enumerate(self.options):
        widget = self.query_one(f"#option-{i}")
        widget.remove_class("selected")
        if i == self.selected_option:
            widget.add_class("selected")
```

---

## Summary: Key Patterns to Adopt

### 1. Widget Replacement over Visibility

```python
# Don't do this:
widget.display = False

# Do this:
await widget.remove()
await container.mount(new_widget)
```

### 2. Focus with `call_after_refresh`

```python
# After mounting:
self.call_after_refresh(widget.focus)

# In on_blur:
def on_blur(self, event):
    self.call_after_refresh(self.focus)
```

### 3. Focus Settings for Interactive Widgets

```python
class MyWidget(Container):
    can_focus = True
    can_focus_children = False
```

### 4. Declarative Key Bindings

```python
BINDINGS = [
    Binding("up", "move_up", show=False),
    Binding("down", "move_down", show=False),
    Binding("enter", "select", show=False),
    Binding("escape", "cancel", show=False),
]
```

### 5. Message-Based Communication

```python
class MyWidget(Container):
    class Selected(Message):
        def __init__(self, value: str):
            super().__init__()
            self.value = value

    def action_select(self):
        self.post_message(self.Selected(self.current_value))
```

### 6. State Enum for Mode Tracking

```python
class BottomApp(StrEnum):
    Input = auto()
    Config = auto()
    Approval = auto()

self._current_bottom_app = BottomApp.Input
```

---

## References

- [Mistral Vibe Repository](https://github.com/mistralai/mistral-vibe)
- [Textual Documentation](https://textual.textualize.io/)
- Source files analyzed:
  - `vibe/cli/textual_ui/app.py`
  - `vibe/cli/textual_ui/widgets/config_app.py`
  - `vibe/cli/textual_ui/widgets/approval_app.py`
  - `vibe/cli/textual_ui/widgets/chat_input/container.py`
  - `vibe/cli/textual_ui/widgets/chat_input/body.py`
  - `vibe/cli/textual_ui/widgets/chat_input/text_area.py`
