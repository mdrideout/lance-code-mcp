"""Init wizard using Textual."""

from dataclasses import dataclass

from rich.panel import Panel
from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.binding import Binding
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


LOCAL_MODELS = [
    ("bge-small (~33MB, 384 dim) - fastest", "BAAI/bge-small-en-v1.5", 384),
    ("bge-base (~130MB, 768 dim) - recommended", "BAAI/bge-base-en-v1.5", 768),
    ("bge-large (~330MB, 1024 dim) - highest quality", "BAAI/bge-large-en-v1.5", 1024),
]


class ProviderScreen(Screen):
    """Select embedding provider."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Select embedding provider:", classes="title"),
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
                classes="buttons",
            ),
            id="content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.exit(WizardResult(cancelled=True))
        elif event.button.id == "continue":
            radio_set = self.query_one("#provider-set", RadioSet)
            selected = radio_set.pressed_button
            if selected:
                provider = selected.id
                if provider == "local":
                    self.app.push_screen(ModelScreen())
                else:
                    self.app.push_screen(ComingSoonScreen(provider))


class ModelScreen(Screen):
    """Select local embedding model."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Select embedding model:", classes="title"),
            RadioSet(
                *[
                    RadioButton(name, id=value, value=(i == 1))  # bge-base default
                    for i, (name, value, _) in enumerate(LOCAL_MODELS)
                ],
                id="model-set",
            ),
            Horizontal(
                Button("Continue", variant="primary", id="continue"),
                Button("Back", id="back"),
                classes="buttons",
            ),
            id="content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "continue":
            radio_set = self.query_one("#model-set", RadioSet)
            selected = radio_set.pressed_button
            if selected:
                model = selected.id
                dims = next(d for _, v, d in LOCAL_MODELS if v == model)
                self.app.push_screen(ConfirmScreen("local", model, dims))


class ComingSoonScreen(Screen):
    """Cloud provider coming soon message."""

    def __init__(self, provider: str):
        super().__init__()
        self.provider = provider

    def compose(self) -> ComposeResult:
        yield Header()
        key_name = f"{self.provider.upper()}_API_KEY"
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
        yield Vertical(
            Label(f"{self.provider.title()} - Coming Soon!", classes="title"),
            Static(
                f"{self.provider.title()} embeddings will be available in a future release.\n\n"
                "To prepare, add your API key to .mcp.json:"
            ),
            Static(Panel(Syntax(json_example, "json", theme="monokai"))),
            Horizontal(
                Button("Use Local Instead", variant="primary", id="use-local"),
                Button("Cancel", id="cancel"),
                classes="buttons",
            ),
            id="content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.exit(WizardResult(cancelled=True))
        elif event.button.id == "use-local":
            self.app.switch_screen(ModelScreen())


class ConfirmScreen(Screen):
    """Confirm and start initialization."""

    def __init__(self, provider: str, model: str, dimensions: int):
        super().__init__()
        self._provider = provider
        self._model = model
        self._dimensions = dimensions

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Ready to Initialize", classes="title"),
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
                classes="buttons",
            ),
            id="content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.exit(WizardResult(cancelled=True))
        elif event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "init":
            self.app.exit(
                WizardResult(
                    provider=self._provider,
                    model=self._model,
                    dimensions=self._dimensions,
                )
            )


class InitWizardApp(App):
    """Init wizard application."""

    TITLE = "Lance Code RAG Setup"

    CSS = """
    #content {
        align: center middle;
        padding: 2;
    }
    .title {
        text-style: bold;
        margin-bottom: 1;
    }
    .buttons {
        margin-top: 2;
    }
    Button {
        margin-right: 1;
    }
    RadioSet {
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(ProviderScreen())

    def action_quit(self) -> None:
        self.exit(WizardResult(cancelled=True))


def run_init_wizard() -> WizardResult:
    """Run the init wizard and return the result."""
    app = InitWizardApp()
    result = app.run()
    # Handle case where app exits without returning a result
    if result is None:
        return WizardResult(cancelled=True)
    return result
