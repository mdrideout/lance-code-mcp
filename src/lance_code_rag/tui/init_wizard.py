"""Init wizard screens for Lance Code RAG.

These screens are designed to be pushed onto the main app's screen stack,
not run as a separate Textual app (which doesn't work with nested apps).
"""

from collections.abc import Callable
from dataclasses import dataclass

from rich.panel import Panel
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RadioButton, RadioSet, Static


@dataclass
class WizardResult:
    """Result from the init wizard."""

    provider: str = ""
    model: str = ""
    dimensions: int = 0
    cancelled: bool = False


# Callback type for wizard completion
WizardCallback = Callable[[WizardResult], None]

# (display_name, model_id, widget_id, dimensions)
LOCAL_MODELS = [
    ("bge-small (~33MB, 384 dim) - fastest", "BAAI/bge-small-en-v1.5", "bge-small", 384),
    ("bge-base (~130MB, 768 dim) - recommended", "BAAI/bge-base-en-v1.5", "bge-base", 768),
    ("bge-large (~330MB, 1024 dim) - highest quality", "BAAI/bge-large-en-v1.5", "bge-large", 1024),
]


CSS = """
#wizard-content {
    align: center middle;
    padding: 2;
}
.wizard-title {
    text-style: bold;
    margin-bottom: 1;
}
.wizard-buttons {
    margin-top: 2;
}
.wizard-buttons Button {
    margin-right: 1;
}
RadioSet {
    margin: 1 0;
}
"""


class ProviderScreen(Screen):
    """Select embedding provider."""

    CSS = CSS

    def __init__(self, on_complete: WizardCallback) -> None:
        super().__init__()
        self._on_complete = on_complete

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Select embedding provider:", classes="wizard-title"),
            RadioSet(
                RadioButton(
                    "Local (FastEmbed) - runs entirely on your machine",
                    id="local",
                    value=True,
                ),
                RadioButton("OpenAI (coming soon)", id="openai"),
                RadioButton("Gemini (coming soon)", id="gemini"),
                id="provider-set",
            ),
            Horizontal(
                Button("Continue", variant="primary", id="continue"),
                Button("Cancel", id="cancel"),
                classes="wizard-buttons",
            ),
            id="wizard-content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
            self._on_complete(WizardResult(cancelled=True))
        elif event.button.id == "continue":
            radio_set = self.query_one("#provider-set", RadioSet)
            selected = radio_set.pressed_button
            if selected:
                provider = selected.id
                if provider == "local":
                    self.app.switch_screen(ModelScreen(self._on_complete))
                else:
                    self.app.switch_screen(ComingSoonScreen(provider, self._on_complete))


class ModelScreen(Screen):
    """Select local embedding model."""

    CSS = CSS

    def __init__(self, on_complete: WizardCallback) -> None:
        super().__init__()
        self._on_complete = on_complete

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Select embedding model:", classes="wizard-title"),
            RadioSet(
                *[
                    RadioButton(name, id=widget_id, value=(i == 1))  # bge-base default
                    for i, (name, _, widget_id, _) in enumerate(LOCAL_MODELS)
                ],
                id="model-set",
            ),
            Horizontal(
                Button("Continue", variant="primary", id="continue"),
                Button("Back", id="back"),
                classes="wizard-buttons",
            ),
            id="wizard-content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.switch_screen(ProviderScreen(self._on_complete))
        elif event.button.id == "continue":
            radio_set = self.query_one("#model-set", RadioSet)
            selected = radio_set.pressed_button
            if selected:
                widget_id = selected.id
                # Find the model by widget_id
                model_id, dims = next(
                    (m, d) for _, m, w, d in LOCAL_MODELS if w == widget_id
                )
                self.app.switch_screen(ConfirmScreen("local", model_id, dims, self._on_complete))


class ComingSoonScreen(Screen):
    """Cloud provider coming soon message."""

    CSS = CSS

    def __init__(self, provider: str, on_complete: WizardCallback) -> None:
        super().__init__()
        self._provider = provider
        self._on_complete = on_complete

    def compose(self) -> ComposeResult:
        key_name = f"{self._provider.upper()}_API_KEY"
        json_example = f"""\
{{
  "mcpServers": {{
    "lance-code-rag": {{
      "env": {{
        "{key_name}": "your-key-here"
      }}
    }}
  }}
}}"""
        yield Header()
        yield Vertical(
            Label(f"{self._provider.title()} - Coming Soon!", classes="wizard-title"),
            Static(
                f"{self._provider.title()} embeddings will be available in a future release.\n\n"
                "To prepare, add your API key to .mcp.json:"
            ),
            Static(Panel(Syntax(json_example, "json", theme="monokai"))),
            Horizontal(
                Button("Use Local Instead", variant="primary", id="use-local"),
                Button("Cancel", id="cancel"),
                classes="wizard-buttons",
            ),
            id="wizard-content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
            self._on_complete(WizardResult(cancelled=True))
        elif event.button.id == "use-local":
            self.app.switch_screen(ModelScreen(self._on_complete))


class ConfirmScreen(Screen):
    """Confirm and start initialization."""

    CSS = CSS

    def __init__(
        self, provider: str, model: str, dimensions: int, on_complete: WizardCallback
    ) -> None:
        super().__init__()
        self._provider = provider
        self._model = model
        self._dimensions = dimensions
        self._on_complete = on_complete

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Ready to Initialize", classes="wizard-title"),
            Static(
                f"Provider: Local (FastEmbed)\n"
                f"Model: {self._model}\n"
                f"Dimensions: {self._dimensions}\n\n"
                "This will:\n"
                "  - Create .lance-code-rag/ directory\n"
                "  - Configure .mcp.json for Claude Code/Cursor\n"
                "  - Index your codebase"
            ),
            Horizontal(
                Button("Initialize", variant="success", id="init"),
                Button("Back", id="back"),
                Button("Cancel", id="cancel"),
                classes="wizard-buttons",
            ),
            id="wizard-content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
            self._on_complete(WizardResult(cancelled=True))
        elif event.button.id == "back":
            self.app.switch_screen(ModelScreen(self._on_complete))
        elif event.button.id == "init":
            result = WizardResult(
                provider=self._provider,
                model=self._model,
                dimensions=self._dimensions,
            )
            self.app.pop_screen()
            self._on_complete(result)
