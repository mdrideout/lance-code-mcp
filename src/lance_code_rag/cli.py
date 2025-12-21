"""CLI for Lance Code RAG."""

from pathlib import Path

import click

from . import __version__


@click.command()
@click.version_option(version=__version__, prog_name="lcr")
def main() -> None:
    """Lance Code RAG - Semantic code search via MCP.

    Launches the interactive TUI. Use slash commands inside:

        /init     Initialize in this project
        /index    Build or update the index
        /search   Search the codebase
        /status   Show index status
        /help     Show all commands
    """
    from .tui.app import run_app

    run_app(Path.cwd())


if __name__ == "__main__":
    main()
