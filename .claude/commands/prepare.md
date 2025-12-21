# Prepare To Work

Review the following files to understand the project, progress, and what's next.

- @PLAN.md
- @pyproject.toml
- All design docs inside @adr/

## Notes:

- Use astral uv conventions
- Use `uv add` to install all packages - do notn specify versions, get the latest every time.
- Use `uv run` to run commands

## Testing:

- Avoid pointless unit tests
- Focus on critical P0 integration tests to help validate functionality and avoid regressions