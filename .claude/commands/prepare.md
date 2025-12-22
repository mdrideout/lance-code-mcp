# Lance Code RAG

Lance Code RAG is an MCP server powered by FastMCP and LanceDB that provides local semantic search and RAG capabilities to AI agents for codebases, to make it easier for AI Agents to find relevant code in large codebases.

It includes a TUI powered by Textual that makes it easy to setup, initialize, observe, and interact with the codebase indexing, as well as execute search queries manually.

### Prepare to Work

Review the following files to understand the project, progress, and what's next.

- @PLAN.md
- @AGENTS.md
- @pyproject.toml
- All design docs inside @adr/
- File and folder structure

## Important Library Documentation:

Use context7 to perform RAG on libraries and documentation to ensure you are using the latest and correct syntax, and to get examples. Below are links to context7 docs, github repos, and website docs.

- LanceDB - the vector databases used by Lance Code RAG (python library)
  - https://context7.com/lancedb/lancedb
  - https://context7.com/websites/lancedb
  - https://github.com/lancedb/lancedb
  - https://docs.lancedb.com/
- FastMCP - powers this app's MCP server - critical docs for building this MCP server functionality
  - https://context7.com/jlowin/fastmcp
  - https://context7.com/llmstxt/gofastmcp_llms_txt
  - https://context7.com/websites/gofastmcp
- Mistral Vibe CLI - Excellent Textual AI Chat Example to reference when building
  - https://context7.com/mistralai/mistral-vibe
  - https://github.com/mistralai/mistral-vibe
- Elia - Keyboard centric Textual TUI - another excellent Textual TUI reference for examples when building
  - https://context7.com/darrenburns/elia
  - https://github.com/darrenburns/elia
- Textual TUI Documentation - important to use context7 to get the correct syntax and examples when using Textual.
  - https://context7.com/websites/textual_textualize_io
  - https://textual.textualize.io/ 
  - https://github.com/textualize/textual/

## Code Style

- Use Textual UI conventions
- Vertical slice feature organization
- Use Grug development principles, such as single responsibility principle, principle of least astonishment, YAGNI, and KISS. Naked functions over unnecessary classes and abstractions. 

## Notes:

- Use astral uv conventions
- Use `uv add` to install all packages - do notn specify versions, get the latest every time.
- Use `uv run` to run commands
- I will tell you when to create git commits

## Testing:

- Avoid pointless unit tests
- Focus on critical P0 integration tests to help validate functionality and avoid regressions
- Use Textual Pilot to create integration tests