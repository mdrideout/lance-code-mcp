"""CLI for Lance Code RAG."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import LCR_DIR, MCP_CONFIG_FILE, __version__
from .config import get_lcr_dir, load_config, save_config
from .manifest import create_empty_manifest, load_manifest, save_manifest

console = Console()
error_console = Console(stderr=True)


def _detect_lcr_command() -> tuple[str, list[str]]:
    """Detect how to invoke lcr (global install vs uv run).

    Returns:
        Tuple of (command, args) for MCP config.
        Examples:
            ("lcr", ["serve"]) - globally installed
            ("uv", ["run", "--project", "/path/to/lcr", "lcr", "serve"]) - via uv
    """
    # Check if lcr is globally available
    try:
        result = subprocess.run(
            ["which", "lcr"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lcr_path = result.stdout.strip()
            # Make sure it's not just the local .venv
            if ".venv" not in lcr_path:
                return ("lcr", ["serve"])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Check if installed as uv tool
    try:
        result = subprocess.run(
            ["uv", "tool", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "lance-code-rag" in result.stdout:
            return ("lcr", ["serve"])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to uv run with project path
    # Find the lance-code-rag project directory
    lcr_project = _find_lcr_project()
    if lcr_project:
        return ("uv", ["run", "--project", str(lcr_project), "lcr", "serve"])

    # Last resort: assume it will be installed globally
    return ("lcr", ["serve"])


def _find_lcr_project() -> Path | None:
    """Find the lance-code-rag project directory."""
    # Check if we're running from the lcr project itself
    import lance_code_rag

    module_path = Path(lance_code_rag.__file__).parent
    # Go up from src/lance_code_rag to project root
    project_root = module_path.parent.parent
    if (project_root / "pyproject.toml").exists():
        return project_root
    return None


def get_project_root() -> Path:
    """Get the project root directory (current working directory)."""
    return Path.cwd()


def is_initialized(project_root: Path) -> bool:
    """Check if lcr is initialized in the project."""
    return get_lcr_dir(project_root).exists()


def require_initialized(project_root: Path) -> None:
    """Raise an error if lcr is not initialized."""
    if not is_initialized(project_root):
        error_console.print(
            "[red]Error:[/red] Not initialized. Run [bold]lcr init[/bold] first."
        )
        sys.exit(1)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="lcr")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Lance Code RAG - Semantic code search via MCP."""
    if ctx.invoked_subcommand is None:
        # Show banner and help when run without subcommand
        from .tui import print_banner

        print_banner(console)
        console.print()
        console.print(ctx.get_help())


@main.command()
@click.option(
    "--embedding",
    type=click.Choice(["local", "gemini", "openai"]),
    default=None,
    help="Embedding provider (skips interactive wizard)",
)
@click.option(
    "--model",
    default=None,
    help="Specific embedding model name",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration",
)
@click.option(
    "--no-index",
    is_flag=True,
    help="Skip automatic indexing after init",
)
def init(
    embedding: str | None,
    model: str | None,
    force: bool,
    no_index: bool,
) -> None:
    """Initialize lcr in the current project.

    Without flags, runs an interactive wizard.
    With --embedding, uses non-interactive mode.
    """
    from .config import EMBEDDING_MODELS
    from .indexer import run_index

    project_root = get_project_root()
    lcr_dir = get_lcr_dir(project_root)

    if lcr_dir.exists() and not force:
        error_console.print(
            f"[yellow]Warning:[/yellow] {LCR_DIR}/ already exists. Use --force to reinitialize."
        )
        sys.exit(1)

    # Determine configuration via wizard or CLI flags
    if embedding is None:
        # Interactive Textual wizard
        from .tui import run_init_wizard

        result = run_init_wizard()
        if result.cancelled:
            console.print("[dim]Cancelled.[/dim]")
            sys.exit(0)

        provider = result.provider
        model_name = result.model
        dimensions = result.dimensions
    else:
        # CLI flag mode (backward compatible)
        provider = embedding
        model_config = EMBEDDING_MODELS[provider]
        model_name = model if model else model_config["default"]
        dimensions = model_config["dimensions"]

    # Create .lance-code-rag directory
    lcr_dir.mkdir(parents=True, exist_ok=True)

    # Create config with specific model/dimensions
    from .config import LCRConfig

    config = LCRConfig(
        embedding_provider=provider,
        embedding_model=model_name,
        embedding_dimensions=dimensions,
    )
    save_config(config, project_root)

    # Create empty manifest
    manifest = create_empty_manifest()
    save_manifest(manifest, project_root)

    # Create/update .mcp.json
    mcp_command = _create_mcp_config(project_root)

    # Update .gitignore
    _update_gitignore(project_root)

    console.print(
        Panel(
            f"[green]Initialized Lance Code RAG[/green]\n\n"
            f"Embedding provider: [bold]{provider}[/bold]\n"
            f"Model: [bold]{model_name}[/bold]\n"
            f"Config directory: [dim]{lcr_dir}[/dim]\n"
            f"MCP command: [dim]{mcp_command}[/dim]",
            title="lcr init",
        )
    )

    # Auto-run indexing unless --no-index
    if not no_index:
        console.print("\n[bold]Building search index...[/bold]")
        stats = run_index(project_root, force=False, verbose=False, console=console)

        # Display results
        table = Table(title="Indexing Complete")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")

        table.add_row("Files indexed", str(stats.files_scanned))
        table.add_row("Chunks created", str(stats.chunks_added))
        table.add_row("Embeddings computed", str(stats.embeddings_computed))

        console.print(table)
        console.print("\n[green]✓ Ready![/green] MCP server configured in .mcp.json")
        console.print("[dim]Claude Code/Cursor will auto-start the server when you open this project.[/dim]")
    else:
        console.print("\n[dim]Skipped indexing. Run [bold]lcr index[/bold] when ready.[/dim]")


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

    table = Table(title="Lance Code RAG Status")
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
            table.add_row("Index status", "[yellow]Empty - run 'lcr index'[/yellow]")
    else:
        table.add_row("Index status", "[red]No manifest found[/red]")

    console.print(table)


@main.command()
@click.argument("query")
@click.option("-n", "--num-results", default=10, help="Number of results to return")
@click.option("--fuzzy", is_flag=True, help="Enable fuzzy matching for symbol names")
@click.option(
    "--bm25-weight",
    type=float,
    default=0.5,
    help="Weight for BM25 vs semantic search (0.0=pure semantic, 1.0=pure keyword)",
)
def search(query: str, num_results: int, fuzzy: bool, bm25_weight: float) -> None:
    """Search the codebase."""
    from .search import SearchError, run_search

    project_root = get_project_root()
    require_initialized(project_root)

    try:
        results = run_search(
            project_root=project_root,
            query=query,
            limit=num_results,
            fuzzy=fuzzy,
            bm25_weight=bm25_weight,
        )
        _display_search_results(results, console)
    except SearchError as e:
        error_console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _display_search_results(results, console: Console) -> None:
    """Display search results with formatting."""
    from rich.syntax import Syntax

    if not results.results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Search results for:[/bold] {results.query}")
    console.print(
        f"[dim]Found {len(results.results)} results in {results.elapsed_ms:.0f}ms "
        f"(search type: {results.search_type})[/dim]\n"
    )

    type_colors = {
        "function": "green",
        "class": "blue",
        "method": "cyan",
        "module": "yellow",
    }

    for i, result in enumerate(results.results, 1):
        color = type_colors.get(result.type, "white")

        # Header line
        header = f"[bold]{i}.[/bold] [{color}]{result.type}[/{color}]"
        if result.name:
            header += f" [bold]{result.name}[/bold]"
        header += f" [dim](score: {result.score:.3f})[/dim]"
        console.print(header)

        # File location
        console.print(
            f"   [dim]{result.filepath}:{result.start_line}-{result.end_line}[/dim]"
        )

        # Code preview (first 3 lines)
        lines = result.text.split("\n")[:3]
        preview = "\n".join(lines)
        if len(result.text.split("\n")) > 3:
            preview += "\n..."

        # Detect language from filepath
        ext = result.filepath.rsplit(".", 1)[-1] if "." in result.filepath else "text"
        lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "tsx": "typescript"}
        lang = lang_map.get(ext, ext)

        syntax = Syntax(preview, lang, theme="monokai", line_numbers=False)
        console.print(Panel(syntax, border_style="dim"))
        console.print()


@main.command()
@click.option("--port", default=None, type=int, help="Port for SSE transport (default: stdio)")
def serve(port: int | None) -> None:
    """Start the MCP server."""
    from .server import run_server

    project_root = get_project_root()
    require_initialized(project_root)

    if port:
        console.print(f"[bold]Starting MCP server on port {port}...[/bold]")
    else:
        console.print("[bold]Starting MCP server (stdio)...[/bold]")

    run_server(project_root, port=port)


@main.command()
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def clean(force: bool) -> None:
    """Remove the .lance-code-rag directory."""
    project_root = get_project_root()
    lcr_dir = get_lcr_dir(project_root)

    if not lcr_dir.exists():
        console.print(f"[dim]Nothing to clean - {LCR_DIR}/ does not exist.[/dim]")
        return

    if not force:
        if not click.confirm(f"Remove {lcr_dir}?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    shutil.rmtree(lcr_dir)
    console.print(f"[green]Removed {LCR_DIR}/[/green]")


def _create_mcp_config(project_root: Path) -> str:
    """Create or update .mcp.json with lcr server configuration.

    Returns:
        Description of the command that will be used.
    """
    mcp_config_path = project_root / MCP_CONFIG_FILE

    if mcp_config_path.exists():
        with open(mcp_config_path) as f:
            mcp_config = json.load(f)
    else:
        mcp_config = {"mcpServers": {}}

    # Detect how to invoke lcr
    command, args = _detect_lcr_command()

    mcp_config["mcpServers"]["lance-code-rag"] = {
        "command": command,
        "args": args,
        "env": {"LCR_ROOT": str(project_root)},
    }

    with open(mcp_config_path, "w") as f:
        json.dump(mcp_config, f, indent=2)

    # Return description for user feedback
    if command == "lcr":
        return "lcr serve"
    else:
        return f"{command} {' '.join(args)}"


def _update_gitignore(project_root: Path) -> None:
    """Add .lance-code-rag/ to .gitignore if not already present."""
    gitignore_path = project_root / ".gitignore"
    entry = f"{LCR_DIR}/"

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if entry in content or LCR_DIR in content:
            return  # Already present
        # Append to existing file
        with open(gitignore_path, "a") as f:
            f.write(f"\n# Lance Code RAG\n{entry}\n")
    else:
        # Create new .gitignore
        gitignore_path.write_text(f"# Lance Code RAG\n{entry}\n")


if __name__ == "__main__":
    main()
