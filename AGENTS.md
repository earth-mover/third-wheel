# Agent Instructions for third-wheel

**Read [CLAUDE.md](CLAUDE.md) first** — it contains the project rules, environment setup, and documentation requirements that apply to all work on this project.

## Agent-Specific Guidance

- **Before starting work**, read the relevant `INTERNAL_DOCS/` files for the area you'll be working in.
- **Track your changes** in `INTERNAL_DOCS/known-issues.md` when fixing tech debt items.
- **When adding features**, write both unit tests AND integration tests. Integration tests catch the bugs that unit tests miss.
- **Changes to `rename.py`** affect both the CLI and the streaming proxy server — test both paths.
- **Use `conftest.create_test_wheel()`** to build synthetic wheels for tests instead of downloading real ones.

## Internal Documentation

Detailed reference docs live in `INTERNAL_DOCS/`:

- **[architecture.md](INTERNAL_DOCS/architecture.md)** — Codebase structure, module relationships, important functions
- **[technical-concepts.md](INTERNAL_DOCS/technical-concepts.md)** — Wheel format, PEP 503, compiled extensions, import rewriting
- **[testing.md](INTERNAL_DOCS/testing.md)** — Test patterns, fixtures, test file locations
- **[proxy-server.md](INTERNAL_DOCS/proxy-server.md)** — Server setup, configuration, full example
- **[commands.md](INTERNAL_DOCS/commands.md)** — Useful CLI commands reference
- **[gotchas.md](INTERNAL_DOCS/gotchas.md)** — Common pitfalls and workarounds
- **[known-issues.md](INTERNAL_DOCS/known-issues.md)** — Tech debt tracker with fix status
