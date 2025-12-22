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

## Important Documentation:

Use context7 to perform RAG on libraries and documentation to ensure you are using the latest and correct syntax, and to get examples.

**Important docs:**

- Mistral Vibe CLI - Excellent Textual AI Chat Example
  - https://context7.com/mistralai/mistral-vibe
  - https://github.com/mistralai/mistral-vibe
- Elia - Keyboard centric Textual TUI
  - https://context7.com/darrenburns/elia
  - https://github.com/darrenburns/elia
- Textual TUI Documentation
  - https://context7.com/websites/textual_textualize_io
  - https://textual.textualize.io/ 
  - https://github.com/textualize/textual/

## Notes:

- Use astral uv conventions
- Use `uv add` to install all packages - do notn specify versions, get the latest every time.
- Use `uv run` to run commands
- I will tell you when to create git commits

## Testing:

- Avoid pointless unit tests
- Focus on critical P0 integration tests to help validate functionality and avoid regressions
- Use Textual Pilot to create integration tests