"""Terminal banner with gradient colors for Lance Code RAG."""

from pathlib import Path

from rich.console import Console
from rich.text import Text

from lance_code_rag import __version__

# Multi-line ASCII art with gradient from lavender (left) to orange (right)
# Note: No leading border chars - we add those dynamically with Rich
BANNER_ASCII = [
    "                                                        ",
    "                                                        ",
    "      L a n c e  C o d e  R A G       \\\\              ",
    "  <=>====>>=============================████====----    ",
    "                                      //                ",
    "                                                        ",
    "                                                        ",
    "  RANDOM TAGLINE HERE                 ",
]

# LanceDB gradient colors (from their website)
GRADIENT_COLORS = [
    "#b7a8e4",  # Lavender (left)
    "#ca9ac2",
    "#e9ac93",
    "#ea7558",
    "#e25a27",  # Orange-red (right)
]

# Left border character (solid vertical line)
BORDER_CHAR = "│"
BORDER_STYLE = "dim #888888"


def interpolate_color(color1: str, color2: str, factor: float) -> str:
    """Interpolate between two hex colors."""
    r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
    r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)

    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)

    return f"#{r:02x}{g:02x}{b:02x}"


def get_gradient_color(position: float, colors: list[str]) -> str:
    """Get color from gradient at position (0.0 to 1.0)."""
    if position <= 0:
        return colors[0]
    if position >= 1:
        return colors[-1]

    segment_size = 1.0 / (len(colors) - 1)
    segment_index = int(position / segment_size)
    segment_index = min(segment_index, len(colors) - 2)

    segment_position = (position - segment_index * segment_size) / segment_size
    return interpolate_color(colors[segment_index], colors[segment_index + 1], segment_position)


def create_gradient_text(text: str, colors: list[str] | None = None) -> Text:
    """Create Rich Text with horizontal gradient."""
    if colors is None:
        colors = GRADIENT_COLORS

    result = Text()
    text_len = len(text)

    for i, char in enumerate(text):
        position = i / max(text_len - 1, 1)
        color = get_gradient_color(position, colors)
        result.append(char, style=f"bold {color}")

    return result


def create_gradient_banner(
    lines: list[str],
    colors: list[str] | None = None,
    show_info: bool = True,
) -> Text:
    """Create Rich Text banner with horizontal gradient and left border.

    Args:
        lines: Lines of ASCII art to render with gradient
        colors: Gradient colors to use
        show_info: Whether to show version and current directory below
    """
    if colors is None:
        colors = GRADIENT_COLORS

    result = Text()
    max_len = max(len(line) for line in lines)

    # Render ASCII art lines with gradient
    for line in lines:
        # Add left border
        result.append(BORDER_CHAR + " ", style=BORDER_STYLE)
        # Add gradient text
        for i, char in enumerate(line):
            position = i / max(max_len - 1, 1)
            color = get_gradient_color(position, colors)
            result.append(char, style=f"bold {color}")
        result.append("\n")

    # Add info lines below (gray, no gradient)
    if show_info:
        # Empty lines for spacing
        result.append(BORDER_CHAR + "\n", style=BORDER_STYLE)
        # Version
        result.append(BORDER_CHAR + "   ", style=BORDER_STYLE)
        result.append(f"v{__version__}\n", style="dim")
        # Current directory
        result.append(BORDER_CHAR + "   ", style=BORDER_STYLE)
        cwd = str(Path.cwd())
        result.append(f"{cwd}\n", style="dim")
        # Empty line for spacing
        result.append(BORDER_CHAR + "\n", style=BORDER_STYLE)

    return result


def print_banner(console: Console | None = None) -> None:
    """Print the Lance Code RAG banner.

    Args:
        console: Rich console to print to
    """
    if console is None:
        console = Console()

    banner = create_gradient_banner(BANNER_ASCII)
    console.print(banner)


if __name__ == "__main__":
    console = Console()
    print_banner(console)
