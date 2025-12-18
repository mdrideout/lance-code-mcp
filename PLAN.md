# Lance Code MCP (lcm) - Architecture Plan

## Executive Summary

Build an installable Python package that provides semantic code search over local codebases via the Model Context Protocol (MCP). The system combines BM25 keyword search, vector embeddings, and fuzzy matching for hybrid retrieval. Runs entirely locally with project-scoped index storage.

**Key Design Goals:**
- CLI command: `lcm`
- Project-local storage at `.lance-code-mcp/`
- Hash-based incremental indexing (only re-index changed files)
- Optional reactive file watching
- Hybrid search: BM25 + semantic vectors + fuzzy matching
- Local-first with optional cloud embeddings (Gemini, OpenAI)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROJECT ROOT                                    │
│                                                                              │
│  ┌───────────────────┐                                                       │
│  │   MCP Client      │      JSON-RPC over stdio                              │
│  │  (Claude Code,    │◄─────────────────────────────────────┐                │
│  │   Desktop, etc)   │                                      │                │
│  └─────────┬─────────┘                                      │                │
│            │                                                │                │
│            ▼                                                │                │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         MCP SERVER (lcm serve)                           ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  ││
│  │  │     TOOLS       │  │   RESOURCES     │  │       PROMPTS           │  ││
│  │  │                 │  │                 │  │                         │  ││
│  │  │ • search_code   │  │ • lcm://status  │  │ • code_review           │  ││
│  │  │ • index_codebase│  │ • lcm://files   │  │ • explain_codebase      │  ││
│  │  │ • get_file_     │  │                 │  │                         │  ││
│  │  │   context       │  │                 │  │                         │  ││
│  │  │ • find_symbol   │  │                 │  │                         │  ││
│  │  │ • fuzzy_find    │  │                 │  │                         │  ││
│  │  └────────┬────────┘  └────────┬────────┘  └────────────┬────────────┘  ││
│  │           │                    │                        │               ││
│  │           └────────────────────┼────────────────────────┘               ││
│  │                                ▼                                        ││
│  │  ┌───────────────────────────────────────────────────────────────────┐  ││
│  │  │                       RAG PIPELINE                                 │  ││
│  │  │                                                                    │  ││
│  │  │   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌─────────┐  │  ││
│  │  │   │  INDEXER  │───▶│  CHUNKER  │───▶│ EMBEDDER  │───▶│ STORAGE │  │  ││
│  │  │   │  (hash-   │    │(tree-sitter)   │(local/    │    │(LanceDB)│  │  ││
│  │  │   │  based)   │    │           │    │ cloud)    │    │         │  │  ││
│  │  │   └───────────┘    └───────────┘    └───────────┘    └─────────┘  │  ││
│  │  │                                                                    │  ││
│  │  │   ┌───────────────────────────────────────────────────────────┐   │  ││
│  │  │   │                    HYBRID SEARCHER                         │   │  ││
│  │  │   │                                                            │   │  ││
│  │  │   │    Vector Search ────┐                                     │   │  ││
│  │  │   │    (semantic)        │                                     │   │  ││
│  │  │   │                      ├───▶ Reranker ───▶ Results           │   │  ││
│  │  │   │    BM25 Search ──────┤                                     │   │  ││
│  │  │   │    (keyword)         │                                     │   │  ││
│  │  │   │                      │                                     │   │  ││
│  │  │   │    Fuzzy Search ─────┘                                     │   │  ││
│  │  │   │    (edit distance)                                         │   │  ││
│  │  │   └───────────────────────────────────────────────────────────┘   │  ││
│  │  │                                                                    │  ││
│  │  │   ┌───────────────────────────────────────────────────────────┐   │  ││
│  │  │   │                   FILE WATCHER (optional)                  │   │  ││
│  │  │   │         Monitors changes → triggers incremental update     │   │  ││
│  │  │   └───────────────────────────────────────────────────────────┘   │  ││
│  │  └───────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                       │
│                                      ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     .lance-code-mcp/  (PROJECT LOCAL)                  │  │
│  │                                                                        │  │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │   │   lancedb/  │  │ manifest.   │  │  config.    │  │   index.    │  │  │
│  │   │             │  │   json      │  │   json      │  │   lock      │  │  │
│  │   │ • vectors   │  │             │  │             │  │             │  │  │
│  │   │ • fts index │  │ • file      │  │ • settings  │  │ • prevents  │  │  │
│  │   │ • metadata  │  │   hashes    │  │ • embedding │  │   concurrent│  │  │
│  │   │             │  │ • tree hash │  │   provider  │  │   writes    │  │  │
│  │   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
lance-code-mcp/
├── pyproject.toml              # Package config, entry point: lcm
├── README.md
├── LICENSE
├── install.sh                  # curl installer
└── src/lance_code_mcp/
    ├── __init__.py
    ├── cli.py                  # CLI commands (lcm)
    ├── server.py               # MCP server
    ├── indexer.py              # Orchestrates indexing pipeline
    ├── chunker.py              # Tree-sitter parsing
    ├── embeddings.py           # Local/Gemini/OpenAI providers
    ├── search.py               # Hybrid + fuzzy search
    ├── watcher.py              # File watching (optional)
    ├── merkle.py               # Merkle tree for change detection
    ├── manifest.py             # Manifest file I/O
    └── config.py               # Configuration management
```

## Module Specifications

### Module: merkle.py

**Purpose**: Merkle tree construction, comparison, and updates for change detection

**Key Classes/Functions**:

| Name | Description |
|------|-------------|
| `MerkleTree` | Main class representing the tree |
| `MerkleNode` | Node class (file or directory) |
| `build_tree(root_path, exclude_patterns)` | Scan filesystem and build tree (ignores symlinks) |
| `compare_trees(old_tree, new_tree)` | Find changed/new/deleted files |
| `update_node(tree, filepath, new_hash)` | Update single file and rehash ancestors |

**MerkleNode Properties**:

| Property | Type | Description |
|----------|------|-------------|
| `hash` | str | SHA256 hash |
| `type` | "file" \| "directory" | Node type |
| `path` | str | Relative path from root |
| `children` | dict | Child nodes (directories only) |
| `size` | int | File size (files only) |
| `mtime` | float | Modification time (files only) |
| `chunks` | list[str] | Chunk IDs (files only) |

**Compare Result Structure**:

```
{
  "new": ["path/to/new_file.py", ...],
  "modified": ["path/to/changed_file.py", ...],
  "deleted": ["path/to/removed_file.py", ...]
}
```

---

---

## CLI Specification (cli.py)

**Command:** `lcm`

### Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `lcm init` | `--embedding [local\|gemini\|openai]` | Initialize in project, create .mcp.json |
| `lcm index` | `--watch`, `--force`, `--verbose` | Index codebase (incremental by default) |
| `lcm status` | None | Show index status, stale files count |
| `lcm search` | `QUERY`, `-n`, `--fuzzy`, `--bm25-weight` | Search from CLI |
| `lcm serve` | `--port` | Start MCP server |
| `lcm clean` | None | Remove .lance-code-mcp directory |

### Index Behavior

```
lcm index
    │
    ▼
┌─────────────────────────────┐
│ Load manifest.json          │
│ (existing Merkle tree)      │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ Build current Merkle tree   │
│ from filesystem             │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ Compare trees               │
│ (traverse from root)        │
└─────────────┬───────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
[Changes found]    [No changes]
    │                   │
    ▼                   ▼
Process only        "Index up to date"
changed files       Exit
    │
    ▼
Update LanceDB
(add/update/delete chunks)
    │
    ▼
Save new manifest.json
```

---

## Merkle Tree Change Detection

### Overview

Use a Merkle tree that mirrors the directory structure. Each node contains a hash computed from its children, allowing efficient detection of which subtrees have changed.

```
                    ┌─────────────────┐
                    │   ROOT HASH     │
                    │   (project)     │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
      ┌──────────┐    ┌──────────┐    ┌──────────┐
      │   src/   │    │  tests/  │    │  lib/    │
      │  hash_A  │    │  hash_B  │    │  hash_C  │
      └────┬─────┘    └────┬─────┘    └──────────┘
           │               │
     ┌─────┴─────┐        ...
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐
│ main.py │ │utils.py │
│ hash_1  │ │ hash_2  │
└─────────┘ └─────────┘
```

### Manifest File Structure

Location: `.lance-code-mcp/manifest.json`

```
{
  "version": 1,
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "tree": {
    "hash": "root_hash",
    "type": "directory",
    "children": {
      "src": {
        "hash": "hash_A",
        "type": "directory",
        "children": {
          "main.py": {
            "hash": "sha256_of_content",
            "type": "file",
            "size": 1234,
            "mtime": 1702834567.123,
            "chunks": ["chunk_id_1", "chunk_id_2"],
            "indexed_at": "ISO timestamp"
          },
          "utils.py": {
            "hash": "sha256_of_content",
            "type": "file",
            ...
          }
        }
      },
      "tests": {
        "hash": "hash_B",
        "type": "directory",
        "children": { ... }
      }
    }
  },
  "stats": {
    "total_files": 42,
    "total_chunks": 256
  }
}
```

### Hash Computation Rules

| Node Type | Hash Formula |
|-----------|--------------|
| File | `SHA256(file_content)` |
| Directory | `SHA256(sorted([child_name + child_hash for child in children]))` |
| Root | Same as directory (top-level) |

### Merkle Tree Traversal Algorithm

```
compare_trees(stored_tree, current_tree):
    │
    ▼
Compare root hashes
    │
    ├── Same ──▶ No changes, done
    │
    ▼ Different
For each child in current_tree:
    │
    ├── Child not in stored ──▶ NEW (index entire subtree)
    │
    ├── Child hash matches ──▶ UNCHANGED (skip entire subtree)
    │
    └── Child hash differs:
        │
        ├── Is file ──▶ MODIFIED (re-index single file)
        │
        └── Is directory ──▶ Recurse into subtree
        
For each child in stored but not in current:
    └── DELETED (remove from index)
```

### Benefits of Merkle Tree Approach

| Benefit | Description |
|---------|-------------|
| Skip unchanged subtrees | If `src/` hash unchanged, skip all files in src/ |
| O(log n) best case | Only traverse changed branches |
| Natural batching | Process entire new directories together |
| Future-proof | Enables partial sync, remote comparison |

### Single-File Re-indexing

When a file changes, re-index immediately (not batched):

```
File change detected: src/auth.py
           │
           ▼
    ┌──────────────────┐
    │ Delete old chunks │
    │ for src/auth.py   │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Parse with       │
    │ tree-sitter      │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Generate         │
    │ embeddings       │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Insert new       │
    │ chunks to Lance  │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Update Merkle    │
    │ tree (rehash     │
    │ ancestors)       │
    └──────────────────┘
```

### Merkle Tree Update After File Change

When `src/utils.py` changes:

1. Recompute `hash(src/utils.py)` from new content
2. Recompute `hash(src/)` from updated children
3. Recompute `hash(root)` from updated children
4. Save updated manifest

---

## Reactive File Watching

### Modes

| Mode | Command | Behavior |
|------|---------|----------|
| One-shot | `lcm index` | Index once and exit |
| Watch | `lcm index --watch` | Index then watch for changes continuously |
| Server | `lcm serve` | Check staleness on search, lazy re-index |

### Watch Mode Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FILE WATCHER                       │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  watchfiles  │───▶│     Debounce Queue       │   │
│  │  (inotify/   │    │  (500ms window)          │   │
│  │   fsevents)  │    │  Collects changed paths  │   │
│  └──────────────┘    └───────────┬──────────────┘   │
│                                  │                   │
│                                  ▼                   │
│                      ┌──────────────────────────┐   │
│                      │   Process Each File      │   │
│                      │   (sequentially)         │   │
│                      │                          │   │
│                      │   For each changed file: │   │
│                      │   1. Re-chunk            │   │
│                      │   2. Re-embed            │   │
│                      │   3. Update LanceDB      │   │
│                      │   4. Update Merkle node  │   │
│                      └──────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Debouncing Strategy

- Collect file change events for 500ms
- After debounce window closes, process each file individually
- Single-file processing ensures index is always consistent
- Merkle tree ancestors updated after each file

### Server Staleness Handling

When MCP server receives a search request:

```
Search request received
         │
         ▼
Compare root hash (fast, in-memory)
         │
         ├── Match ──▶ Proceed with search
         │
         ▼ Mismatch (stale)
Proceed with search anyway
         │
         ▼
Return results WITH staleness warning:
{
  "results": [...],
  "warning": "Index is stale. 3 files changed since last index.",
  "stale_files": ["src/auth.py", "src/utils.py", "lib/helpers.py"]
}
```

**Rationale**: Never block the user. Stale results are better than no results. User can trigger re-index if needed via `index_codebase` tool or `lcm index` CLI.

---

## Fuzzy Search with LanceDB

### LanceDB Fuzzy Capabilities

LanceDB supports fuzzy full-text search via its FTS index. Key features:

| Feature | Description |
|---------|-------------|
| Edit distance | Match terms within N edits (typos) |
| Prefix matching | Match partial words |
| Tokenization | Language-aware word splitting |
| Boosting | Boost exact matches over fuzzy |

### Search Types

| Search Type | Use Case | Implementation |
|-------------|----------|----------------|
| **Vector** | "code that handles authentication" | Embedding similarity |
| **BM25** | "getUserById" (exact keywords) | Full-text search |
| **Fuzzy** | "getUsrByld" (typos) | FTS with fuzziness |
| **Hybrid** | Best of all worlds | Combine + rerank |

### Fuzzy Search Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `fuzziness` | Max edit distance (0-2) | 1 |
| `prefix_length` | Min chars before fuzzy kicks in | 2 |
| `fuzzy_boost` | Score multiplier for fuzzy matches | 0.8 |
| `exact_boost` | Score multiplier for exact matches | 1.2 |

### Search Tool Parameters

The `search_code` tool accepts:

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Search query |
| `top_k` | int | Results to return (default: 10) |
| `search_type` | enum | "hybrid", "vector", "bm25", "fuzzy" |
| `bm25_weight` | float | 0.0-1.0, weight for keyword vs semantic |
| `fuzziness` | int | 0-2, edit distance for fuzzy matching |
| `file_filter` | string | Glob pattern to filter files |

### Hybrid Search Algorithm

```
Query: "authentcation handler" (note typo)
           │
           ├───────────────────────────────────────────┐
           │                                           │
           ▼                                           ▼
┌─────────────────────┐                    ┌─────────────────────┐
│   Vector Search     │                    │   FTS Search        │
│                     │                    │                     │
│ Embed query →       │                    │ BM25: "authentcation│
│ Find similar chunks │                    │       handler"      │
│                     │                    │                     │
│ Results: semantic   │                    │ Fuzzy: matches      │
│ matches             │                    │ "authentication"    │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          │              ┌───────────────┐           │
          └─────────────▶│   Reranker    │◀──────────┘
                         │               │
                         │ RRF or Linear │
                         │ Combination   │
                         └───────┬───────┘
                                 │
                                 ▼
                         Final ranked results
```

---

## Embedding Cache

### Purpose

Avoid re-computing embeddings for unchanged code chunks. Significant cost/time savings when re-indexing modified files.

### Cache Key Strategy

```
cache_key = SHA256(chunk_text)
```

The chunk content hash serves as the cache key. If the exact same code appears (even in a different file), reuse the embedding.

### Storage

Store cached embeddings in a separate LanceDB table:

**Table: embedding_cache**

| Column | Type | Description |
|--------|------|-------------|
| content_hash | string (PK) | SHA256 of chunk text |
| vector | vector[N] | The embedding |
| created_at | timestamp | When cached |

### Cache Flow During Indexing

```
For each chunk to embed:
    │
    ▼
Compute content_hash = SHA256(chunk.text)
    │
    ▼
Lookup in embedding_cache
    │
    ├── HIT ──▶ Use cached vector
    │
    └── MISS ──▶ Generate embedding
                      │
                      ▼
                 Store in cache
                      │
                      ▼
                 Use vector
```

### Cache Benefits

| Scenario | Benefit |
|----------|---------|
| File renamed | All chunks hit cache |
| Minor edit | Unchanged chunks hit cache |
| Duplicate code | Shared embedding |
| Re-index after provider restart | Full cache reuse |

### Cache Invalidation

Cache entries are never invalidated (content-addressed). Old entries naturally become unused. Optional: periodic cleanup of entries not referenced by any current chunk.

---

### Provider Specification

| Provider | Models | Dimensions | Local? | API Key |
|----------|--------|------------|--------|---------|
| `local` | BAAI/bge-base-en-v1.5, bge-small, nomic-embed-text | 768/384 | Yes | None |
| `gemini` | text-embedding-004 | 768 | No | GEMINI_API_KEY |
| `openai` | text-embedding-3-small, text-embedding-3-large | 1536/3072 | No | OPENAI_API_KEY |

### Local Embedding (Default)

- Framework: sentence-transformers
- No API calls, fully offline
- First run downloads model (~400MB for bge-base)
- Cached in HuggingFace cache directory

### Provider Selection

Priority order:
1. Command line flag: `lcm init --embedding gemini`
2. Config file: `.lance-code-mcp/config.json`
3. Environment variable: `LCM_EMBEDDING_PROVIDER`
4. Default: `local`

### Embedding Consistency

**Critical**: Cannot mix embedding providers in same index. If provider changes:
- Detect dimension mismatch
- Prompt user to re-index with `--force`
- Store provider info in manifest

---

## Storage Specification

### Directory Structure

```
project-root/
├── .lance-code-mcp/           # All lcm data (add to .gitignore)
│   ├── lancedb/               # LanceDB database files
│   │   ├── code_chunks.lance/ # Vector + FTS index
│   │   └── embedding_cache.lance/ # Cached embeddings
│   ├── manifest.json          # Merkle tree, file→chunk mappings
│   ├── config.json            # User settings
│   └── index.lock             # Prevents concurrent indexing
├── .mcp.json                   # MCP client configuration
└── (project files)
```

### .gitignore Entry

`lcm init` should append to .gitignore:

```
# Lance Code MCP
.lance-code-mcp/
```

### LanceDB Schema

**Table: code_chunks**

| Column | Type | Index | Description |
|--------|------|-------|-------------|
| id | string | Primary | Unique chunk ID (filepath:start_line) |
| vector | vector[N] | IVF_PQ | Embedding (N = provider dimensions) |
| text | string | FTS | Code content (for BM25 + fuzzy) |
| content_hash | string | - | SHA256 of text (for cache lookup) |
| filepath | string | - | Absolute path to source file |
| filename | string | - | Just the filename |
| extension | string | - | File extension |
| type | string | - | Chunk type (function, class, etc.) |
| name | string | FTS | Symbol name (for fuzzy find) |
| start_line | int | - | 1-indexed start line |
| end_line | int | - | 1-indexed end line |
| file_hash | string | - | Hash of source file (for staleness) |

**Table: embedding_cache**

| Column | Type | Index | Description |
|--------|------|-------|-------------|
| content_hash | string | Primary | SHA256 of chunk text |
| vector | vector[N] | - | Cached embedding |
| created_at | string | - | ISO timestamp |

### Config File

Location: `.lance-code-mcp/config.json`

```
{
  "version": 1,
  "embedding_provider": "local",
  "embedding_model": "BAAI/bge-base-en-v1.5",
  "embedding_dimensions": 768,
  "extensions": [".py", ".js", ".ts", ".tsx", ".go", ".rs"],
  "exclude_patterns": ["node_modules", ".git", "__pycache__", "venv"],
  "chunk_max_size": 2000,
  "chunk_overlap": 200,
  "watch_debounce_ms": 500
}
```

---

## MCP Server Specification

### Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `search_code` | query, top_k, search_type, bm25_weight, fuzziness, file_filter | Hybrid search |
| `fuzzy_find` | symbol_name, symbol_type | Find symbols with typo tolerance |
| `index_codebase` | force | Trigger indexing from AI |
| `get_file_context` | filepath, include_related | Get file + related chunks |
| `get_stale_status` | None | Check if index is outdated |

### Resources

| URI | Description |
|-----|-------------|
| `lcm://status` | Index status, stats, staleness |
| `lcm://config` | Current configuration |
| `lcm://files` | List of indexed files with metadata |

### Prompts

| Prompt | Description |
|--------|-------------|
| `code_review` | Review a specific file |
| `explain_codebase` | Understand overall architecture |
| `find_similar` | Find similar implementations |

### Server Startup Sequence

```
lcm serve
    │
    ▼
Check .lance-code-mcp/ exists
    │
    ├── No ──▶ Error: "Run 'lcm init' first"
    │
    ▼ Yes
Load config.json
    │
    ▼
Load manifest.json (if exists)
    │
    ▼
Open LanceDB connection
    │
    ▼
Register tools/resources/prompts
    │
    ▼
Enter stdio message loop

Note: Server does NOT auto-index. If index is missing or stale,
search tools return warnings. User triggers indexing explicitly
via CLI or index_codebase tool.
```

---

## Dependencies

### Required

| Package | Version | Purpose |
|---------|---------|---------|
| mcp | >=1.2.0 | MCP server framework |
| lancedb | >=0.15.0 | Vector + FTS database |
| tree-sitter | >=0.23.0 | Code parsing |
| tree-sitter-python | >=0.23.0 | Python grammar |
| tree-sitter-javascript | >=0.23.0 | JS grammar |
| tree-sitter-typescript | >=0.23.0 | TS grammar |
| tree-sitter-go | >=0.23.0 | Go grammar |
| tree-sitter-rust | >=0.23.0 | Rust grammar |
| sentence-transformers | >=3.0.0 | Local embeddings |
| click | >=8.0.0 | CLI framework |
| rich | >=13.0.0 | CLI output |
| watchfiles | >=0.21.0 | File watching |
| filelock | >=3.12.0 | Concurrent access |

### Optional

| Package | Purpose |
|---------|---------|
| openai | OpenAI embeddings |
| google-generativeai | Gemini embeddings |

---

## MCP Configuration (.mcp.json)

Created by `lcm init`:

```
{
  "mcpServers": {
    "lance-code-mcp": {
      "command": "lcm",
      "args": ["serve"],
      "env": {
        "LCM_ROOT": "/absolute/path/to/project"
      }
    }
  }
}
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| LCM_ROOT | Project root override | Current directory |
| LCM_EMBEDDING_PROVIDER | Embedding provider | "local" |
| LCM_EMBEDDING_MODEL | Specific model name | Provider default |
| OPENAI_API_KEY | OpenAI API key | - |
| GEMINI_API_KEY | Gemini API key | - |

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Not initialized | "Run 'lcm init' to set up this project" |
| Index missing | "Run 'lcm index' to build the search index" |
| Provider mismatch | "Index was built with X, but config specifies Y. Run 'lcm index --force'" |
| API key missing | "Set GEMINI_API_KEY environment variable" |
| File parse error | Log warning, skip file, continue |
| Concurrent index | Wait for lock or error |

---

## Implementation Order

### Phase 1: Core Setup
- Package structure with pyproject.toml
- CLI skeleton with click (`lcm` command)
- Config and manifest modules
- Basic logging

### Phase 2: Indexing Pipeline
- Tree-sitter chunker (Python first, then others)
- Local embedding provider
- LanceDB storage with FTS index
- Manifest/hash tracking
- Incremental indexing logic

### Phase 3: Search
- Hybrid search (vector + BM25)
- Fuzzy search integration
- Reranking strategies
- CLI search command

### Phase 4: MCP Server
- FastMCP server setup
- All tools implementation
- Resources and prompts
- Staleness checking

### Phase 5: File Watching
- watchfiles integration
- Debouncing logic
- `--watch` mode
- Server lazy re-index

### Phase 6: Additional Providers
- OpenAI embeddings
- Gemini embeddings
- Provider switching logic

### Phase 7: Polish
- Rich progress bars
- Error messages
- Documentation
- install.sh script
- PyPI publishing

---

## Design Decisions (Resolved)

| Decision | Resolution |
|----------|------------|
| Change detection | Merkle tree mirroring directory structure |
| Re-index granularity | Single file (immediate, not batched) |
| Stale index behavior | Return results with warning, never block |
| Large files | Chunk normally (no size limit skip) |
| Binary files | Skip (detect via null bytes or extension) |
| Embedding cache | Cache embeddings keyed by chunk content hash |
| Multi-root workspaces | Not supported (single project root only) |
| Symlinks | Ignore (do not follow, avoids cycles) |