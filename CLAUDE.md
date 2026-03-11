# Claude Instructions for third-wheel

**third-wheel** is a tool to rename Python wheel packages for multi-version installation.

## High-Level Rules

### Code Quality

- **Read before writing.** Understand existing code before modifying it.
- **Simple solutions.** Prefer straightforward code over abstractions. Don't over-engineer.
- **Test everything you write.** Unit tests for logic, integration tests for end-to-end workflows.
- **Write integration tests.** Don't just test units in isolation — test the full pipeline (download, rename, install, import).
- **Run tests before committing.** `uv run pytest tests/` and `uv run ruff check` must pass.
- **Respect the wheel spec.** After renaming, filename, directory name, and METADATA `Name:` must all match. RECORD hashes must be recomputed.

### Documentation

- **Document as you go.** Every commit that changes behavior must update relevant docs. Don't leave it for later.
- **INTERNAL_DOCS/** for architecture, testing, known issues, and implementation details.
- **README.md** for user-facing changes (new commands, changed flags, new features).
- **Docstrings** on all public functions.

### Environment

- Python 3.11+, use `uv run` for all Python commands
- `from __future__ import annotations` in all files
- `click` for CLI, `rich` for terminal output
- Ruff for linting/formatting, pyright for type checking

### Git Workflow

- Feature branches off `main`
- PRs require passing CI
- Releases: create a GitHub Release (triggers PyPI publish)

## Internal Documentation

Detailed reference docs live in `INTERNAL_DOCS/`:

- **[planning.md](INTERNAL_DOCS/planning.md)** — Current priorities, decisions log, cross-session notes
- **[architecture.md](INTERNAL_DOCS/architecture.md)** — Codebase structure, module relationships, important functions
- **[technical-concepts.md](INTERNAL_DOCS/technical-concepts.md)** — Wheel format, PEP 503, compiled extensions
- **[testing.md](INTERNAL_DOCS/testing.md)** — Test patterns, fixtures, test file locations
- **[proxy-server.md](INTERNAL_DOCS/proxy-server.md)** — Server setup and configuration
- **[commands.md](INTERNAL_DOCS/commands.md)** — Useful CLI commands reference
- **[gotchas.md](INTERNAL_DOCS/gotchas.md)** — Common pitfalls and workarounds
- **[known-issues.md](INTERNAL_DOCS/known-issues.md)** — Tech debt tracker with fix status
