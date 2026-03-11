# Agent Instructions for third-wheel

This document provides context and guidance for AI assistants working on the third-wheel project.

## Project Overview

**third-wheel** is a tool to rename Python wheel packages for multi-version installation. The primary use case is regression testing where you need both `icechunk` (v2) and `icechunk_v1` (renamed v1) installed simultaneously.

## Key Technical Concepts

### Wheel File Format (PEP 427)

- Wheels are ZIP files with `.whl` extension
- Structure: `{package}/`, `{package}-{version}.dist-info/`
- METADATA file contains package name, version, dependencies
- RECORD file contains SHA256 hashes of all files
- WHEEL file contains wheel metadata (generator, tags)

### Compiled Extensions Challenge

- `.so`/`.pyd` files contain `PyInit_{name}` symbol baked into binary
- This symbol MUST match the filename for Python to load the extension
- **Workaround**: If extension uses underscore prefix (e.g., `_icechunk_python.cpython-*.so`), parent directory can be renamed while keeping the `.so` filename unchanged
- Python imports `icechunk_v1._icechunk_python` and finds `PyInit__icechunk_python` correctly

### PEP 503 Simple Repository API

- Package indexes use this standard (PyPI, Anaconda.org)
- Root endpoint `/simple/` lists all projects
- Project endpoint `/simple/{project}/` lists all wheels
- Supports JSON variant (PEP 691) but HTML is most common

## Codebase Structure

```text
src/third_wheel/
├── __init__.py      # Package exports, version from _version.py (hatch-vcs)
├── cli.py           # Click-based CLI with rich output
├── download.py      # PEP 503 index client using pypi-simple
├── patch.py         # Patch dependency references in wheels
├── rename.py        # Core wheel manipulation logic
├── run.py           # PEP 723 inline script runner with rename support
├── sync.py          # Project-level sync: read pyproject.toml, download+rename+install
└── server/          # Proxy server for on-the-fly renaming
    ├── __init__.py
    ├── app.py       # FastAPI application with PEP 503 endpoints
    ├── config.py    # Configuration (TOML + CLI) with name normalization
    ├── html.py      # PEP 503 HTML generation
    ├── stream.py    # Wheel streaming and on-the-fly renaming
    └── upstream.py  # Async HTTP client for upstream indexes

tests/
├── conftest.py              # Shared fixtures for venv creation
├── test_rename.py           # Unit tests for rename functions
├── test_download.py         # Wheel tag parsing tests
├── test_run.py              # PEP 723 metadata parsing and rename tests
├── test_patch.py            # Dependency patching tests
├── test_config.py           # Server configuration tests
├── test_server.py           # Proxy server endpoint tests
├── test_integration.py      # Import rewriting tests
├── test_dual_install.py     # Multi-package isolation tests
├── test_icechunk_integration.py  # Real icechunk wheel tests
└── fixtures/
    └── dual-install/        # Example project for multi-version install

examples/
├── cli_rename.py                # CLI rename demo (urllib3 v1 + v2)
└── icechunk_dual_version.py     # Inline annotation demo (icechunk v1 + v2)
```

## Important Functions

### `rename.py`

- `rename_wheel(wheel_path, new_name, output_dir, update_imports)` - Main entry point
- `_update_python_imports(content, old_name, new_name)` - Regex-based import rewriting
- `inspect_wheel(wheel_path)` - Analyze wheel structure, detect extensions
- `normalize_name(name)` - PEP 503 name normalization (public)
- `parse_wheel_filename(filename)` - Parse wheel filename into components (public)
- `compute_record_hash(data)` - SHA256 for RECORD file (public)

### `download.py`

- `download_compatible_wheel(package, output_dir, index_url, version)` - Download best match
- `best_wheel(packages, compatible_tags)` - Select most compatible wheel
- `parse_wheel_tags(filename)` - Extract platform tags from wheel name (handles dot-separated tags like `py2.py3`)

### `patch.py`

- `patch_wheel(wheel_path, old_dep, new_dep, output_dir)` - Rewrite dependency references inside a wheel
- `patch_wheel_from_bytes(data, filename, old_dep, new_dep)` - In-memory variant for proxy streaming

### `run.py`

- `parse_pep723_metadata(script)` - Extract PEP 723 inline metadata block
- `extract_renames_from_comments(toml_str)` - Parse `"pkg_v1",  # pkg<2` comment annotations
- `extract_renames_from_tool_table(toml_str)` - Parse `[tool.third-wheel]` structured metadata
- `parse_cli_renames(rename_args)` - Parse `--rename "pkg<2=pkg_v1"` CLI args (splits on last `=`)
- `run_script(script_path, cli_renames, index_url, ...)` - Orchestrate download, rename, and `uv run`
- `cache_dir()` - Return the platform cache directory for third-wheel (public)
- `rename_cache_key(original, version, new_name)` - Compute cache key for a renamed wheel (public)
- `prepare_wheels(renames, wheel_dir, index_url, python_version, verbose)` - Download and rename wheels into a directory (public)

### `sync.py`

- `parse_renames_from_pyproject(path)` - Read rename specs from pyproject.toml (comment annotations + structured `[tool.third-wheel]` metadata, merged with structured form winning on conflict)
- `sync(renames, *, index_url, find_links, python_version, force, verbose)` - Orchestrate download+rename+install into the current venv. Uses same caching as `run`. Supports local wheels via `find_links`. The `force` param skips cache and re-downloads.
- `add_rename_to_pyproject(path, spec)` - Add or update a rename entry in pyproject.toml's `[tool.third-wheel]` section. Creates the section if it doesn't exist; updates in place if the same `new-name` already exists.
- `add_rename_to_script(path, spec)` - Add or update a rename entry in a PEP 723 inline script. Adds the new package to dependencies and creates/updates a `[tool.third-wheel]` renames entry within the metadata block.
- `_find_wheel_in_directory(find_links, original, version)` - Find the highest-version matching wheel in a local directory
- `_prepare_wheels_from_find_links(renames, wheel_dir, find_links)` - Copy and rename wheels from a local directory instead of downloading
- `get_pyproject_config(path)` - Read optional config (e.g., `index-url`) from `[tool.third-wheel]` (public)

**Relationship between `run` and `sync`:** `run` is for standalone PEP 723 inline scripts (creates an isolated temporary environment via `uv run`). `sync` is for project-level virtual environments — it reads renames from `pyproject.toml` and installs into the current venv via `uv pip install`. Both share the same rename spec parsing (`extract_renames_from_comments`, `extract_renames_from_tool_table`) and caching infrastructure (`cache_dir`, `rename_cache_key`, `prepare_wheels`) from `run.py`.

### `cli.py`

- Rich console output for nice formatting
- `run` command uses `ignore_unknown_options=True` for arg passthrough to scripts
- `sync_cmd` reads renames from pyproject.toml + CLI flags, merges them, calls `sync()`
- `add_cmd` parses a CLI rename spec, writes it to pyproject.toml (or PEP 723 script via `--script`), optionally runs sync
- `cache_clean_cmd` removes cached wheels from sync and/or run operations

## Testing Patterns

### Dual-Install Tests

Tests create isolated venvs and install both original and renamed packages to verify:

1. Both packages import without errors
2. Module `__file__` paths are distinct
3. Internal import chains stay within each package
4. No `sys.modules` contamination
5. No leaked references to old package name in renamed package

### Test Wheel Creation

Use `conftest.create_test_wheel()` to create synthetic wheels with version-tagged functions:

```python
v1_wheel = create_test_wheel(tmp_path, "mypkg", "1.0.0")
v1_renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=tmp_path)
```

### Running Tests

```bash
uv run python -m pytest tests/           # All tests
uv run python -m pytest tests/test_rename.py  # Unit tests only
uv run python -m pytest -m integration   # Integration tests (slower, network)
```

## Common Tasks

### Adding a New CLI Command

1. Add function in `cli.py` with `@main.command()` decorator
2. Use Click options/arguments
3. Use `console.print()` for output, `err_console.print()` for errors
4. Handle exceptions and call `sys.exit(1)` on error

### Modifying Import Rewriting

The regex patterns in `_update_python_imports()` handle:

- `from pkg import x`
- `from pkg.submodule import x`
- `import pkg`
- `import pkg as alias`

Be careful with word boundaries (`\b`) to avoid partial matches.

### Adding Test Coverage

- Unit tests go in `test_rename.py`
- Tag/download tests go in `test_download.py`
- Run/metadata parsing tests go in `test_run.py`
- Patch tests go in `test_patch.py`
- Server config tests go in `test_config.py`
- Server endpoint tests go in `test_server.py`
- Import rewriting tests go in `test_integration.py`
- Multi-package isolation tests go in `test_dual_install.py`
- Sync/add tests go in `test_sync.py` (use the self-referential pattern — third-wheel can rename its own wheel — or the `--find-links` approach with locally-built test wheels)
- Real wheel tests go in `test_icechunk_integration.py` with `@pytest.mark.integration`

## Dependencies

Core:

- `click` - CLI framework
- `packaging` - Version parsing, platform tags
- `pypi-simple` - PEP 503 index client
- `rich` - Pretty terminal output

Server (optional):

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `httpx` - Async HTTP client

## Proxy Server

The proxy server enables `uv sync` to install renamed packages without manual wheel downloading.

### How It Works

1. Start proxy: `third-wheel serve -u <upstream> -r "pkg=pkg_v1:<version>"`
2. Proxy serves `/simple/pkg_v1/` endpoint with renamed wheel links
3. When uv requests the wheel, proxy downloads from upstream, renames on-the-fly, serves renamed wheel
4. uv installs `pkg_v1` as a normal package

### Server Modules

- `config.py`: Loads TOML config or CLI args, handles PEP 503 name normalization
- `app.py`: FastAPI routes for `/simple/`, `/simple/{project}/`, `/simple/{project}/{filename}`
- `upstream.py`: Async client to fetch packages from upstream indexes
- `stream.py`: Downloads wheel, calls `rename_wheel_from_bytes()`, returns renamed bytes
- `html.py`: Generates PEP 503 HTML with rewritten filenames

### Configuration Options

```toml
[tool.uv]
extra-index-url = ["http://127.0.0.1:8123/simple/"]
prerelease = "allow"
index-strategy = "unsafe-best-match"  # Required for mixing indexes
resolution = "highest"
```

## Implementing Multi-Version Install

The simplest approach is `third-wheel run` with a PEP 723 script. See examples/ for working demos.

For project-level setups, use `third-wheel sync` (simpler) or the proxy server (for `uv sync` integration):

### Using `third-wheel sync` (recommended for most cases)

```bash
# Add a rename to pyproject.toml and install
third-wheel add "icechunk<2=icechunk_v1" --sync

# Or sync from existing pyproject.toml config
third-wheel sync
```

### Using the proxy server (for full `uv sync` integration)

### Step 1: Install third-wheel with server extras

```bash
pip install third-wheel[server]
# or
uvx --with third-wheel[server] third-wheel serve --help
```

### Step 2: Start the proxy server

```bash
third-wheel serve \
    -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    -r "icechunk=icechunk_v1:<2" \
    --port 8123
```

### Step 3: Configure pyproject.toml

```toml
[project]
name = "my-project"
requires-python = ">=3.12"
dependencies = [
    "icechunk>=2.0.0.dev0",  # v2 from nightly
    "icechunk_v1",            # v1 renamed, from proxy
]

[tool.uv]
extra-index-url = [
    "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple",
    "http://127.0.0.1:8123/simple/",
]
prerelease = "allow"
index-strategy = "unsafe-best-match"
resolution = "highest"
```

### Step 4: Install with uv sync

```bash
uv sync
```

### Step 5: Use both versions

```python
import icechunk      # v2
import icechunk_v1   # v1

# Both are fully isolated and functional
```

### Reference Implementation

See `tests/fixtures/dual-install/` for a complete working example with:

- `pyproject.toml` - Full uv configuration
- `README.md` - Detailed usage instructions

## Git Workflow

- All development happens on feature branches off `main`
- Pre-commit hooks (via `prek`) run ruff check, ruff format, and markdownlint on commit
- CI runs all unit tests and integration tests on PRs
- Releases are triggered by creating a GitHub Release (see RELEASE.md)

## Environment

- Python 3.11+ required
- Use `uv` for environment management: `uv sync`, `uv run pytest`
- Ruff for linting and formatting
- Pyright for type checking (strict mode)

## Gotchas

1. **Anaconda.org doesn't provide digests** - Use `verify=False` when downloading
2. **Version specifiers with .dev releases** - Use `>=2.0.0.dev0` not `>=2.0.0a0` for dev releases
3. **pytest.skip() in fixtures** - Use assertions instead to avoid hiding failures
4. **pypi-simple is sync** - For async proxy, need to wrap or use httpx directly
5. **Wheel filenames must match internal metadata** - After renaming, filename, directory name, and METADATA Name must all match

## Known Issues and Tech Debt

Issues discovered during deep review (2026-03-10). Mark items DONE as they are fixed.

### Pre-existing (in main before sync feature)

- [ ] **CRITICAL: `parse_wheel_filename` build tag heuristic** (`rename.py:39-40`) — Checks `parts[2][0].isdigit()` to detect build tags. Should count from end instead (python/abi/platform are always last 3 parts).
- [ ] **CRITICAL: `rename_wheel_from_bytes` version fallback** (`rename.py:296`) — `rsplit("-", 1)` on dist-info name silently falls back to `"0.0.0"`, producing a corrupt wheel.
- [ ] **HIGH: Code duplication rename_wheel vs rename_wheel_from_bytes** (`rename.py`) — ~100 lines of identical core logic. Extract a shared helper.
- [ ] **MEDIUM: `_find_package_dir` misses namespace packages** (`rename.py`) — Only detects packages with `__init__.py`, missing PEP 420 implicit namespace packages.
- [x] **MEDIUM: `_has_server_extras()` is dead code** (`run.py:320-328`) — Never called. Removed.
- [ ] **LOW: `inspect_wheel` stores booleans as strings** (`rename.py:411`) — `"True"/"False"` strings instead of proper bools.
- [ ] **TEST: `rename_wheel_from_bytes`** — Zero tests for this public function.
- [ ] **TEST: `inspect_wheel`** — Zero tests for this public function.
- [ ] **TEST: `run_script`** — Zero unit tests for core orchestration.

### New (introduced with sync feature)

- [x] **HIGH: `add_rename_to_pyproject` regex not section-scoped** (`sync.py`) — Fixed: regex searches now scoped to after `[tool.third-wheel]` header, bounded by next section.
- [x] **HIGH: `sync_cmd` silently ignores missing explicit `--pyproject`** (`cli.py`) — Fixed: errors when explicitly provided path doesn't exist.
- [x] **HIGH: `add_cmd --sync` drops options** (`cli.py`) — Fixed: now reads pyproject config for index-url (matching `sync_cmd` behavior).
- [x] **MEDIUM: `_detect_installer` no existence check** (`sync.py`) — Fixed: falls back to default `uv pip install` when neither conda python path exists.
- [x] **MEDIUM: `cache_clean_cmd` mutual exclusion check after early return** (`cli.py`) — Fixed: validation moved before cache existence check.
- [x] **MEDIUM: `get_pyproject_config` catches bare Exception** (`sync.py`) — Fixed: now catches only `TOMLDecodeError`.
- [ ] **MEDIUM: `cache_dir()` ignores XDG_CACHE_HOME** (`run.py:331-339`) — Falls back to `~/.cache/` directly instead of respecting `$XDG_CACHE_HOME`.
- [x] **LOW: Inconsistent error emoji across CLI commands** — Fixed: all commands now use `🔧 Error:`.
- [x] **LOW: `sync_cmd` source attribution wrong** (`cli.py`) — Fixed: checks `new_name` in CLI set instead of using dataclass `in`.
- [ ] **TEST: `cache_dir()` env var override** — No test for `THIRD_WHEEL_CACHE_DIR`.
- [ ] **TEST: `rename_cache_key()` stability** — No test for hash stability or collision properties.
- [ ] **TEST: `parse_wheel_filename` invalid inputs** — No negative test cases.
- [ ] **TEST: `rename_wheel(update_imports=False)`** — Untested flag.

## Documentation Updates Are Required With Every Commit

**Every commit that changes functionality MUST include corresponding documentation updates.** This is a hard requirement — do not commit code changes without updating docs.

### Internal docs (AGENTS.md)

- Add a new module → update codebase structure + important functions sections
- Add a new CLI command → update useful commands section
- Add a new test file → update test coverage section
- Change how builds, releases, or CI work → update the relevant sections
- Discover a new gotcha → add to gotchas section

### User-facing docs (README.md)

- Add a new command → add usage examples to README
- Change CLI flags or behavior → update existing README examples
- Add a new feature → add a section with quick-start examples

### Pre-commit checklist

1. `uv run ruff check` passes
2. `uv run pytest` passes (at minimum the non-integration tests)
3. AGENTS.md reflects any structural changes
4. README.md reflects any user-facing changes
5. New test files are listed in AGENTS.md test coverage section

If you are unsure whether a change warrants a docs update, err on the side of updating.

## Useful Commands

```bash
# Run a PEP 723 script with inline rename annotations
uv run third-wheel run examples/cli_rename.py --rename "urllib3<2=urllib3_v1"

# List available wheels for a package
uv run third-wheel download icechunk --list -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

# Inspect a wheel
uv run third-wheel inspect ./icechunk-*.whl

# Rename a wheel
uv run third-wheel rename ./icechunk-*.whl icechunk_v1 -o ./renamed/

# Download and rename in one step
uv run third-wheel download icechunk \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    --version "<2" \
    --rename icechunk_v1 \
    -o ./wheels/

# Sync renamed packages from pyproject.toml into the current venv
uv run third-wheel sync

# Temporary CLI-only sync (not saved to pyproject.toml)
uv run third-wheel sync --rename "icechunk<2=icechunk_v1"

# Force re-download even when cached
uv run third-wheel sync --force --rename "icechunk<2=icechunk_v1"

# Sync from local wheels directory
uv run third-wheel sync --find-links ./dist/ --rename "mypkg<2=mypkg_v1"

# Add a rename to pyproject.toml and install it
uv run third-wheel add "icechunk<2=icechunk_v1" --sync

# Clean all cached wheels
uv run third-wheel cache-clean

# Clean only sync or run caches
uv run third-wheel cache-clean --sync-only
uv run third-wheel cache-clean --run-only
```
