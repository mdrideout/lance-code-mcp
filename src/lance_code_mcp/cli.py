"""CLI for Lance Code MCP."""

import json
import shutil
import sys
from pathlib import Path
from typing import Literal

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import LCM_DIR, MCP_CONFIG_FILE, __version__
from .config import create_default_config, get_lcm_dir, load_config, save_config
from .manifest import create_empty_manifest, load_manifest, save_manifest

console = Console()
error_console = Console(stderr=True)


def get_project_root() -> Path:
    """Get the project root directory (current working directory)."""
    return Path.cwd()


def is_initialized(project_root: Path) -> bool:
    """Check if lcm is initialized in the project."""
    return get_lcm_dir(project_root).exists()


def require_initialized(project_root: Path) -> None:
    """Raise an error if lcm is not initialized."""
    if not is_initialized(project_root):
        error_console.print(
            "[red]Error:[/red] Not initialized. Run [bold]lcm init[/bold] first."
        )
        sys.exit(1)


@click.group()
@click.version_option(version=__version__, prog_name="lcm")
def main() -> None:
    """Lance Code MCP - Semantic code search via MCP."""
    pass


@main.command()
@click.option(
    "--embedding",
    type=click.Choice(["local", "gemini", "openai"]),
    default="local",
    help="Embedding provider to use",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration",
)
def init(embedding: Literal["local", "gemini", "openai"], force: bool) -> None:
    """Initialize lcm in the current project."""
    project_root = get_project_root()
    lcm_dir = get_lcm_dir(project_root)

    if lcm_dir.exists() and not force:
        error_console.print(
            f"[yellow]Warning:[/yellow] {LCM_DIR}/ already exists. Use --force to reinitialize."
        )
        sys.exit(1)

    # Create .lance-code-mcp directory
    lcm_dir.mkdir(parents=True, exist_ok=True)

    # Create config
    config = create_default_config(embedding)
    save_config(config, project_root)

    # Create empty manifest
    manifest = create_empty_manifest()
    save_manifest(manifest, project_root)

    # Create/update .mcp.json
    _create_mcp_config(project_root)

    # Update .gitignore
    _update_gitignore(project_root)

    console.print(
        Panel(
            f"[green]Initialized Lance Code MCP[/green]\n\n"
            f"Embedding provider: [bold]{embedding}[/bold]\n"
            f"Config directory: [dim]{lcm_dir}[/dim]\n\n"
            f"Next steps:\n"
            f"  1. Run [bold]lcm index[/bold] to build the search index\n"
            f"  2. Run [bold]lcm serve[/bold] to start the MCP server",
            title="lcm init",
        )
    )


@main.command()
@click.option("--watch", is_flag=True, help="Watch for file changes after indexing (Phase 5)")
@click.option("--force", is_flag=True, help="Force full re-index")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def index(watch: bool, force: bool, verbose: bool) -> None:
    """Index the codebase for semantic search."""
    from .indexer import run_index

    project_root = get_project_root()
    require_initialized(project_root)

    if watch:
        console.print("[yellow]--watch not implemented yet.[/yellow] Coming in Phase 5.")
        return

    console.print("[bold]Indexing codebase...[/bold]")

    stats = run_index(project_root, force=force, verbose=verbose, console=console)

    # Display results
    table = Table(title="Indexing Complete")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Files scanned", str(stats.files_scanned))
    table.add_row("New files", str(stats.files_new))
    table.add_row("Modified files", str(stats.files_modified))
    table.add_row("Deleted files", str(stats.files_deleted))
    table.add_row("Chunks indexed", str(stats.chunks_added))
    table.add_row("Chunks removed", str(stats.chunks_deleted))
    table.add_row("Embeddings computed", str(stats.embeddings_computed))
    table.add_row("Embeddings from cache", str(stats.embeddings_cached))

    console.print(table)

    if stats.files_new == 0 and stats.files_modified == 0 and stats.files_deleted == 0:
        console.print("[green]Index is up to date.[/green]")
    else:
        console.print("[green]Indexing complete![/green]")


@main.command()
def status() -> None:
    """Show index status and statistics."""
    project_root = get_project_root()
    require_initialized(project_root)

    config = load_config(project_root)
    manifest = load_manifest(project_root)

    table = Table(title="Lance Code MCP Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Project root", str(project_root))
    table.add_row("Embedding provider", config.embedding_provider)
    table.add_row("Embedding model", config.embedding_model)

    if manifest:
        table.add_row("Indexed files", str(manifest.stats.total_files))
        table.add_row("Total chunks", str(manifest.stats.total_chunks))
        table.add_row("Last updated", manifest.updated_at.isoformat())
        if manifest.tree:
            table.add_row("Index status", "[green]Ready[/green]")
        else:
            table.add_row("Index status", "[yellow]Empty - run 'lcm index'[/yellow]")
    else:
        table.add_row("Index status", "[red]No manifest found[/red]")

    console.print(table)


@main.command()
@click.argument("query")
@click.option("-n", "--num-results", default=10, help="Number of results to return")
@click.option("--fuzzy", is_flag=True, help="Enable fuzzy matching")
@click.option(
    "--bm25-weight",
    type=float,
    default=0.5,
    help="Weight for BM25 vs semantic search (0.0-1.0)",
)
def search(query: str, num_results: int, fuzzy: bool, bm25_weight: float) -> None:
    """Search the codebase."""
    project_root = get_project_root()
    require_initialized(project_root)

    console.print("[yellow]Not implemented yet.[/yellow] Coming in Phase 3.")
    console.print(f"  query: {query}")
    console.print(f"  num_results: {num_results}")
    console.print(f"  fuzzy: {fuzzy}")
    console.print(f"  bm25_weight: {bm25_weight}")


@main.command()
@click.option("--port", default=None, type=int, help="Port for HTTP transport (default: stdio)")
def serve(port: int | None) -> None:
    """Start the MCP server."""
    project_root = get_project_root()
    require_initialized(project_root)

    console.print("[yellow]Not implemented yet.[/yellow] Coming in Phase 4.")
    if port:
        console.print(f"  port: {port}")
    else:
        console.print("  transport: stdio")


@main.command()
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def clean(force: bool) -> None:
    """Remove the .lance-code-mcp directory."""
    project_root = get_project_root()
    lcm_dir = get_lcm_dir(project_root)

    if not lcm_dir.exists():
        console.print(f"[dim]Nothing to clean - {LCM_DIR}/ does not exist.[/dim]")
        return

    if not force:
        if not click.confirm(f"Remove {lcm_dir}?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    shutil.rmtree(lcm_dir)
    console.print(f"[green]Removed {LCM_DIR}/[/green]")


def _create_mcp_config(project_root: Path) -> None:
    """Create or update .mcp.json with lcm server configuration."""
    mcp_config_path = project_root / MCP_CONFIG_FILE

    if mcp_config_path.exists():
        with open(mcp_config_path) as f:
            mcp_config = json.load(f)
    else:
        mcp_config = {"mcpServers": {}}

    mcp_config["mcpServers"]["lance-code-mcp"] = {
        "command": "lcm",
        "args": ["serve"],
        "env": {"LCM_ROOT": str(project_root)},
    }

    with open(mcp_config_path, "w") as f:
        json.dump(mcp_config, f, indent=2)


def _update_gitignore(project_root: Path) -> None:
    """Add .lance-code-mcp/ to .gitignore if not already present."""
    gitignore_path = project_root / ".gitignore"
    entry = f"{LCM_DIR}/"

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if entry in content or LCM_DIR in content:
            return  # Already present
        # Append to existing file
        with open(gitignore_path, "a") as f:
            f.write(f"\n# Lance Code MCP\n{entry}\n")
    else:
        # Create new .gitignore
        gitignore_path.write_text(f"# Lance Code MCP\n{entry}\n")


if __name__ == "__main__":
    main()
