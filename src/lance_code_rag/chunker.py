"""Tree-sitter based code chunking for Lance Code RAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

ChunkType = Literal["function", "class", "method", "module"]

# Map file extensions to language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    # Future: add more languages
    # ".js": "javascript",
    # ".ts": "typescript",
    # ".go": "go",
    # ".rs": "rust",
}

# Node types to extract per language
EXTRACTABLE_NODES: dict[str, list[str]] = {
    "python": ["function_definition", "class_definition"],
}


@dataclass
class Chunk:
    """A semantic code chunk extracted from a source file."""

    text: str
    type: ChunkType
    name: str  # Empty string for module-level chunks
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed

    @property
    def content_hash(self) -> str:
        """SHA256 hash of the text content."""
        return hashlib.sha256(self.text.encode()).hexdigest()


class Chunker:
    """Extracts semantic code chunks using tree-sitter parsing."""

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}

    def _get_parser(self, language: str) -> Parser | None:
        """Get or create parser for language. Returns None if unsupported."""
        if language in self._parsers:
            return self._parsers[language]

        if language == "python":
            lang = Language(tspython.language())
            parser = Parser(lang)
            self._parsers[language] = parser
            self._languages[language] = lang
            return parser

        # Unsupported language
        return None

    def chunk_file(self, filepath: Path, content: str | None = None) -> list[Chunk]:
        """
        Extract semantic chunks from a source file.

        Args:
            filepath: Path to the source file
            content: Optional content (if already read). If None, reads from filepath.

        Returns:
            List of Chunk objects. Returns module-level chunk on parse error.
        """
        # Read content if not provided
        if content is None:
            try:
                content = filepath.read_text()
            except OSError:
                return []

        # Empty file
        if not content.strip():
            return []

        # Get language from extension
        language = self.get_language_for_extension(filepath.suffix)
        if language is None:
            return [self._create_fallback_chunk(content, filepath)]

        # Get parser
        parser = self._get_parser(language)
        if parser is None:
            return [self._create_fallback_chunk(content, filepath)]

        # Parse the code
        try:
            tree = parser.parse(content.encode())
        except Exception:
            return [self._create_fallback_chunk(content, filepath)]

        # Extract chunks based on language
        if language == "python":
            return self._chunk_python(content, tree.root_node)

        return [self._create_fallback_chunk(content, filepath)]

    def _chunk_python(self, content: str, root_node) -> list[Chunk]:
        """Extract chunks from Python AST."""
        chunks: list[Chunk] = []
        content_bytes = content.encode()

        def visit_node(node, parent_class: str | None = None):
            node_type = node.type

            if node_type == "function_definition":
                name = self._get_python_name(node)
                text = content_bytes[node.start_byte:node.end_byte].decode()
                chunk_type: ChunkType = "method" if parent_class else "function"
                chunks.append(Chunk(
                    text=text,
                    type=chunk_type,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))

            elif node_type == "class_definition":
                name = self._get_python_name(node)
                text = content_bytes[node.start_byte:node.end_byte].decode()
                chunks.append(Chunk(
                    text=text,
                    type="class",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
                # Visit children to find methods
                for child in node.children:
                    if child.type == "block":
                        for block_child in child.children:
                            visit_node(block_child, parent_class=name)

            else:
                # Visit children
                for child in node.children:
                    visit_node(child, parent_class)

        visit_node(root_node)

        # If no semantic chunks found, fall back to module chunk
        if not chunks:
            lines = content.split("\n")
            return [Chunk(
                text=content,
                type="module",
                name="",
                start_line=1,
                end_line=len(lines),
            )]

        return chunks

    def _get_python_name(self, node) -> str:
        """Extract the name from a Python function or class definition."""
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode() if isinstance(child.text, bytes) else child.text
        return ""

    def _create_fallback_chunk(self, content: str, filepath: Path) -> Chunk:
        """Create a single module-level chunk as fallback."""
        lines = content.split("\n")
        return Chunk(
            text=content,
            type="module",
            name=filepath.stem,
            start_line=1,
            end_line=len(lines),
        )

    @staticmethod
    def get_language_for_extension(extension: str) -> str | None:
        """Map file extension to language name."""
        return EXTENSION_TO_LANGUAGE.get(extension)

    @staticmethod
    def is_supported_extension(extension: str) -> bool:
        """Check if extension is supported for semantic parsing."""
        return extension in EXTENSION_TO_LANGUAGE
