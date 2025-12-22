"""Terminal banner with gradient colors for Lance Code RAG."""

import random
from pathlib import Path

from rich.console import Console
from rich.text import Text

from lance_code_rag import __version__

# Multi-line ASCII art with gradient from lavender (left) to orange (right)
# Note: No leading border chars - we add those dynamically with Rich
BANNER_ASCII = [
    "                                                                  ",
    "L a n c e  C o d e  R A G",
    "                                                                  ",
    "                                                 \\\\             ",
    "  <=>====>>=========================================████====----  ",
    "                                                  //              ",
    "                                                                  ",
]

# Random taglines shown at startup
TAGLINES = [
    "Wield the lance. Conquer the codebase.",
    "An enchanted lance for slaying bugs.",
    "Quest forth. Slay with the lance.",
    "The lance chooses the worthy.",
    "It's dangerous to code alone! Take this.",
    "Brave coder, take up the lance.",
    "Arise, coder. Your lance awaits.",
    "Take up the lance. Begin your quest.",
    "The lance hums with ancient knowledge.",
    "By this lance, no bug shall pass.",
    "The realm of code awaits, brave one.",
    "A worthy lance for a worthy coder.",
    "The lance remembers what you forgot.",
    "The lance whispers forgotten functions.",
    "Where the lance points, answers follow.",
    "You found: Enchanted Lance of Context",
    "Your lance thirsts for bugs.",
    "A new quest begins. The lance glows.",
    "Your inventory: one legendary lance.",
    "Sound the horn. Ready the lance.",
]


def get_random_tagline() -> str:
    """Get a random tagline for the banner."""
    return random.choice(TAGLINES)


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
    center: bool = False,
    width: int | None = None,
    tagline: str | None = None,
) -> Text:
    """Create Rich Text banner with horizontal gradient.

    Args:
        lines: Lines of ASCII art to render with gradient
        colors: Gradient colors to use
        show_info: Whether to show version and current directory below
        center: Whether to center shorter lines within the banner width
        width: Width to center within (if None, uses max line length)
        tagline: Optional tagline to display below banner art
    """
    if colors is None:
        colors = GRADIENT_COLORS

    result = Text()
    max_len = max(len(line) for line in lines)

    # Use max line length as the centering width if not specified
    if width is None:
        width = max_len

    # Render ASCII art lines with gradient
    for line in lines:
        # Center shorter lines within the banner width
        if center and len(line) < width:
            padding = (width - len(line)) // 2
            result.append(" " * padding)

        # Add gradient text
        for i, char in enumerate(line):
            position = i / max(max_len - 1, 1)
            color = get_gradient_color(position, colors)
            result.append(char, style=f"bold {color}")
        result.append("\n")

    # Add tagline if provided
    if tagline:
        # Center tagline within banner width
        if center and len(tagline) < width:
            padding = (width - len(tagline)) // 2
            result.append(" " * padding)
        # Render tagline with gradient
        for i, char in enumerate(tagline):
            position = i / max(len(tagline) - 1, 1)
            color = get_gradient_color(position, colors)
            result.append(char, style=f"bold {color}")
        result.append("\n")

    # Add info lines below (gray, no gradient)
    if show_info:
        # Empty line for spacing
        result.append("\n")
        # Version
        result.append("   ")
        result.append(f"v{__version__}\n", style="dim")
        # Current directory
        result.append("   ")
        cwd = str(Path.cwd())
        result.append(f"{cwd}\n", style="dim")
        # Empty line for spacing
        result.append("\n")

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
