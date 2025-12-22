# Lance Code RAG (lcr) - Architecture Plan

## Executive Summary

Build an installable Python package that provides semantic code search over local codebases via the Model Context Protocol (MCP). The system combines BM25 keyword search, vector embeddings, and fuzzy matching for hybrid retrieval. Runs entirely locally with project-scoped index storage.

**Key Design Goals:**
- CLI command: `lcr`
- Project-local storage at `.lance-code-rag/`
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
│  │                         MCP SERVER (lcr serve)                           ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  ││
│  │  │     TOOLS       │  │   RESOURCES     │  │       PROMPTS           │  ││
│  │  │                 │  │                 │  │                         │  ││
│  │  │ • search_code   │  │ • lcr://status  │  │ • code_review           │  ││
│  │  │ • index_codebase│  │ • lcr://files   │  │ • explain_codebase      │  ││
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
│  │                     .lance-code-rag/  (PROJECT LOCAL)                  │  │
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
lance-code-rag/
├── pyproject.toml              # Package config, entry point: lcr
├── README.md
├── PLAN.md                     # This file
├── adr/
│   └── 001-adr-merkle-trees.md # ADR: Why content-addressed Merkle trees
├── src/lance_code_rag/
│   ├── __init__.py             # Package constants (LCR_DIR, etc.)
│   ├── cli.py                  # CLI commands (lcr) ✅
│   ├── config.py               # Configuration management ✅
│   ├── manifest.py             # Manifest file I/O ✅
│   ├── server.py               # MCP server (stub)
│   ├── indexer.py              # Orchestrates indexing pipeline ✅
│   ├── chunker.py              # Tree-sitter parsing ✅
│   ├── embeddings.py           # Local embedding provider ✅
│   ├── storage.py              # LanceDB wrapper ✅
│   ├── search.py               # Hybrid + fuzzy search ✅
│   ├── watcher.py              # File watching (stub)
│   └── merkle.py               # Merkle tree for change detection ✅
└── tests/
    ├── conftest.py             # Shared fixtures
    ├── fixtures/sample_project/ # Test codebase (Python, JS)
    └── integration/
        ├── test_cli.py         # CLI integration tests (8 tests)
        ├── test_indexing.py    # Indexing integration tests (7 tests)
        ├── test_merkle.py      # Merkle tree tests (23 tests)
        └── test_search.py      # Search integration tests (12 tests)
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

**Command:** `lcr`

### Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `lcr init` | `--embedding [local\|gemini\|openai]` | Initialize in project, create .mcp.json |
| `lcr index` | `--watch`, `--force`, `--verbose` | Index codebase (incremental by default) |
| `lcr status` | None | Show index status, stale files count |
| `lcr search` | `QUERY`, `-n`, `--fuzzy`, `--bm25-weight` | Search from CLI |
| `lcr serve` | `--port` | Start MCP server |
| `lcr clean` | None | Remove .lance-code-rag directory |

### Index Behavior

```
lcr index
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

Location: `.lance-code-rag/manifest.json`

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
| One-shot | `lcr index` | Index once and exit |
| Watch | `lcr index --watch` | Index then watch for changes continuously |
| Server | `lcr serve` | Check staleness on search, lazy re-index |

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

**Rationale**: Never block the user. Stale results are better than no results. User can trigger re-index if needed via `index_codebase` tool or `lcr index` CLI.

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
1. Command line flag: `lcr init --embedding gemini`
2. Config file: `.lance-code-rag/config.json`
3. Environment variable: `LCR_EMBEDDING_PROVIDER`
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
├── .lance-code-rag/           # All lcr data (add to .gitignore)
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

`lcr init` should append to .gitignore:

```
# Lance Code MCP
.lance-code-rag/
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

Location: `.lance-code-rag/config.json`

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
| `lcr://status` | Index status, stats, staleness |
| `lcr://config` | Current configuration |
| `lcr://files` | List of indexed files with metadata |

### Prompts

| Prompt | Description |
|--------|-------------|
| `code_review` | Review a specific file |
| `explain_codebase` | Understand overall architecture |
| `find_similar` | Find similar implementations |

### Server Startup Sequence

```
lcr serve
    │
    ▼
Check .lance-code-rag/ exists
    │
    ├── No ──▶ Error: "Run 'lcr init' first"
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

Created by `lcr init`:

```
{
  "mcpServers": {
    "lance-code-rag": {
      "command": "lcr",
      "args": ["serve"],
      "env": {
        "LCR_ROOT": "/absolute/path/to/project"
      }
    }
  }
}
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| LCR_ROOT | Project root override | Current directory |
| LCR_EMBEDDING_PROVIDER | Embedding provider | "local" |
| LCR_EMBEDDING_MODEL | Specific model name | Provider default |
| OPENAI_API_KEY | OpenAI API key | - |
| GEMINI_API_KEY | Gemini API key | - |

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Not initialized | "Run 'lcr init' to set up this project" |
| Index missing | "Run 'lcr index' to build the search index" |
| Provider mismatch | "Index was built with X, but config specifies Y. Run 'lcr index --force'" |
| API key missing | "Set GEMINI_API_KEY environment variable" |
| File parse error | Log warning, skip file, continue |
| Concurrent index | Wait for lock or error |

---

## Implementation Order

### Phase 1: Core Setup ✅ COMPLETE
- [x] Package structure with pyproject.toml (hatchling build backend)
- [x] CLI skeleton with click (`lcr` command)
- [x] Config module with Pydantic models (`config.py`)
- [x] Manifest module with Pydantic models (`manifest.py`)
- [x] All CLI commands: init, index, status, search, serve, clean
- [x] Environment variable overrides (LCR_EMBEDDING_PROVIDER, LCR_EMBEDDING_MODEL)
- [x] Test infrastructure with fixture codebase

**Implemented files:**
- `src/lance_code_rag/__init__.py` - Package constants
- `src/lance_code_rag/cli.py` - Full CLI implementation
- `src/lance_code_rag/config.py` - Pydantic config with env overrides
- `src/lance_code_rag/manifest.py` - Pydantic manifest I/O
- `src/lance_code_rag/{server,indexer,chunker,embeddings,search,watcher,merkle}.py` - Stubs

**Test structure:**
```
tests/
├── conftest.py                    # cli_runner, sample_project fixtures
├── fixtures/sample_project/       # Curated test codebase (Python, JS)
└── integration/
    └── test_cli.py                # 8 CLI integration tests
```

### Phase 2: Indexing Pipeline ✅ COMPLETE
- [x] Tree-sitter chunker (Python first)
- [x] Local embedding provider (sentence-transformers, BAAI/bge-base-en-v1.5)
- [x] LanceDB storage with code_chunks and embedding_cache tables
- [x] Merkle tree implementation for change detection
- [x] mtime optimization (skip content hashing when mtime+size unchanged)
- [x] Manifest/hash tracking
- [x] Incremental indexing logic
- [x] `lcr index` command with --force and --verbose flags
- [x] Integration tests for indexing (7 tests)
- [x] Comprehensive Merkle tree tests (23 tests)
- [x] ADR documenting Merkle tree architecture decision

**Implemented files:**
- `src/lance_code_rag/merkle.py` - Merkle tree with mtime optimization (MerkleNode, MerkleTree, TreeDiff, TreeBuildStats)
- `src/lance_code_rag/storage.py` - LanceDB wrapper (CodeChunk, CachedEmbedding, Storage)
- `src/lance_code_rag/chunker.py` - Tree-sitter parsing (Chunk, Chunker)
- `src/lance_code_rag/embeddings.py` - Local embeddings (EmbeddingProvider, LocalEmbeddingProvider)
- `src/lance_code_rag/indexer.py` - Pipeline orchestration (IndexStats, Indexer, run_index)
- `tests/integration/test_indexing.py` - 7 indexing integration tests
- `tests/integration/test_merkle.py` - 23 Merkle tree tests
- `adr/001-adr-merkle-trees.md` - Architecture decision record

**Key optimizations:**
- Embedding cache: Content-addressed by chunk hash, avoids re-embedding unchanged code
- mtime cache: Reuses file hashes when mtime+size unchanged, reduces I/O on incremental scans

### Phase 3: Search ✅ COMPLETE
- [x] Vector search using LanceDB
- [x] BM25 full-text search using LanceDB FTS
- [x] Hybrid search combining vector + BM25 with RRF reranking
- [x] Fuzzy search for symbol names (typo tolerance using SequenceMatcher)
- [x] Reranking (Reciprocal Rank Fusion)
- [x] `lcr search` CLI command implementation
- [x] Search result formatting with Rich syntax highlighting
- [x] Integration tests for search (12 tests)

**Implemented files:**
- `src/lance_code_rag/search.py` - SearchEngine class with vector, FTS, hybrid, fuzzy search
- `tests/integration/test_search.py` - 12 search integration tests

**Key features:**
- Lazy FTS index creation (created on first search, not during indexing)
- RRF reranking for hybrid search (no score normalization needed)
- Fuzzy search on symbol names using SequenceMatcher
- CLI options: `--fuzzy`, `--bm25-weight`, `-n/--num-results`

### Phase 4: Full-Screen TUI 🔄 IN PROGRESS
- [x] Textual-based full-screen TUI (like Claude Code, Gemini CLI)
- [x] ASCII art banner widget at top with random taglines
- [x] Slash command input with history and multiline support
- [x] Status bar showing index state at bottom
- [x] Chat-style output with syntax-highlighted search results
- [x] Inline selection widgets (Mistral Vibe "bottom app swapping" pattern)
- [ ] **E2E validation of /init flow** ← PENDING
- [ ] E2E validation of /remove flow
- [x] TUI-only CLI (removed subcommands, all via slash commands)

**Implemented files:**
- `src/lance_code_rag/tui/app.py` - Main TUI application (LCRApp) with bottom app swapping
- `src/lance_code_rag/tui/app.tcss` - Textual CSS styles
- `src/lance_code_rag/tui/banner.py` - ASCII banner with gradient colors
- `src/lance_code_rag/tui/widgets/` - Widget components:
  - `chat_area.py` - Scrollable chat message area
  - `inline_selector.py` - Inline selection widget (replaces input during prompts)
  - `messages.py` - Message display widgets (UserQuery, AssistantMessage, etc.)
  - `search_input.py` - Command input with history and multiline
  - `status_bar.py` - Bottom status bar
  - `welcome_box.py` - Welcome box with project stats
- `src/lance_code_rag/cli.py` - Simplified to TUI launcher only

**Slash commands:**
- `/init` - Initialize project (inline wizard with provider/model selection)
- `/index` - Index or re-index codebase
- `/search <query>` - Search codebase
- `/status` - Show detailed status
- `/remove` - Remove lance-code-rag from project
- `/clean` - Remove index data only
- `/help`, `/clear`, `/quit`

**Key patterns:**
- Bottom app swapping: InlineSelector replaces SearchInput during prompts
- Message-based communication: Widgets post messages, app handles them
- Flow state machine: Multi-step wizards tracked via `_flow_state` dict
- See `AGENTS.md` for detailed pattern documentation

### Phase 5: MCP Server ← NEXT
- FastMCP server setup
- All tools implementation
- Resources and prompts
- Staleness checking

### Phase 6: File Watching
- watchfiles integration
- Debouncing logic
- `--watch` mode
- Server lazy re-index

### Phase 7: Additional Providers
- OpenAI embeddings
- Gemini embeddings
- Provider switching logic

### Phase 8: Polish
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