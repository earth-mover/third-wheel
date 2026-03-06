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
- `_compute_record_hash(data)` - SHA256 for RECORD file

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

### `cli.py`

- Rich console output for nice formatting
- `run` command uses `ignore_unknown_options=True` for arg passthrough to scripts

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

For project-level setups that need `uv sync`, use the proxy server:

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

## Keeping AGENTS.md Up to Date

**This file must be updated as the project evolves.** When you:

- Add a new module, add it to the codebase structure and important functions sections
- Add a new CLI command, add it to the useful commands section
- Add a new test file, add it to the test coverage section
- Change how builds, releases, or CI work, update the relevant sections
- Discover a new gotcha, add it to the gotchas section

If you are unsure whether a change warrants an update here, err on the side of updating.

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
```
