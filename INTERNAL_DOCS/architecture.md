# Architecture

Module structure, important functions, and dependency map for the third-wheel codebase.

## Codebase Structure

```text
src/third_wheel/
├── __init__.py      # Package exports, version from _version.py (hatch-vcs)
├── build.py         # Build wheels from git URLs or local paths via uv pip wheel
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
├── test_build.py            # Wheel building from git/path sources
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
├── compare_zarr.py              # Git source demo (zarr v2 vs dev from git)
└── icechunk_dual_version.py     # Inline annotation demo (icechunk v1 + v2)
```

## Important Functions

### `rename.py`

- `rename_wheel(wheel_path, new_name, output_dir, update_imports)` - Main entry point (file-based)
- `rename_wheel_from_bytes(wheel_bytes, new_name, update_imports)` - In-memory variant for proxy streaming
- `_rename_wheel_files(zf, old_name, new_name, new_name_normalized, version)` - Shared core logic for both rename functions
- `_update_python_imports(content, old_name, new_name)` - Regex-based import rewriting
- `inspect_wheel(wheel_path)` - Analyze wheel structure, detect extensions
- `normalize_name(name)` - PEP 503 name normalization (public)
- `parse_wheel_filename(filename)` - Parse wheel filename into components (public)
- `compute_record_hash(data)` - SHA256 for RECORD file (public)

### `build.py`

- `build_wheel_from_source(source, output_dir, python_version)` - Build a wheel from a git URL or local path using `uv pip wheel --no-deps`

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
- `RenameSpec` - Dataclass with `original`, `new_name`, `version`, `source` fields. `source_type` property returns `"index"`, `"git"`, or `"path"` based on the `source` prefix.
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

### `cli.py`

- Rich console output for nice formatting
- `run` command uses `ignore_unknown_options=True` for arg passthrough to scripts
- `sync_cmd` reads renames from pyproject.toml + CLI flags, merges them, calls `sync()`
- `add_cmd` parses a CLI rename spec, writes it to pyproject.toml (or PEP 723 script via `--script`), optionally runs sync
- `cache_clean_cmd` removes cached wheels from sync and/or run operations

## Module Relationships

**`run` vs `sync`:** `run` is for standalone PEP 723 inline scripts (creates an isolated temporary environment via `uv run`). `sync` is for project-level virtual environments — it reads renames from `pyproject.toml` and installs into the current venv via `uv pip install`. Both share the same rename spec parsing (`extract_renames_from_comments`, `extract_renames_from_tool_table`) and caching infrastructure (`cache_dir`, `rename_cache_key`, `prepare_wheels`) from `run.py`.

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
