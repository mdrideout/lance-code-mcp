"""Terminal banner with gradient colors for Lance Code RAG."""

from rich.console import Console
from rich.text import Text

# One-line banner with sword
BANNER = "⚔  Lance Code RAG"

# LanceDB gradient colors (from their website)
GRADIENT_COLORS = [
    "#e4d8f8",  # Lavender (left)
    "#e8c4d8",
    "#eba8b0",
    "#eb8880",
    "#e55a2b",  # Orange-red (right)
]


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


def print_banner(console: Console | None = None) -> None:
    """Print the Lance Code RAG banner with gradient."""
    if console is None:
        console = Console()

    banner = create_gradient_text(BANNER)
    console.print(banner)


if __name__ == "__main__":
    console = Console()
    print_banner(console)
