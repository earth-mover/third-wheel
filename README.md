# 🛞 third-wheel

A tool to rename Python wheel packages for multi-version installation.

## Use Case

When you need to install multiple versions of the same Python package in a single environment (e.g., for regression testing), you can use this tool to rename one version's wheel so both can coexist:

```python
# In your test code:
import icechunk_v1  # The v1 version
import icechunk     # The v2 version

# Test that v2 can read data written by v1
```

## Installation

```bash
# Run directly with uvx (no install needed)
uvx third-wheel --help

# Or install as a persistent tool
uv tool install third-wheel

# Or install with pip
pip install third-wheel
```

## Quick Start: `third-wheel run`

The easiest way to use third-wheel is with inline PEP 723 scripts. Write a script
with rename annotations in the dependencies, and `third-wheel run` handles the rest:

```python
# test_versions.py
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "urllib3_v1",  # urllib3<2
#   "urllib3>=2",
# ]
# ///

import urllib3
import urllib3_v1

print(f"urllib3 v2: {urllib3.__version__}")
print(f"urllib3 v1: {urllib3_v1.__version__}")
```

```bash
third-wheel run test_versions.py
```

The comment `# urllib3<2` after `"urllib3_v1"` tells third-wheel: download `urllib3<2`,
rename it to `urllib3_v1`, and make it available alongside the latest `urllib3>=2`.

## End-to-End Example: icechunk v1 + v2

### Using `third-wheel run` (recommended)

```python
# test_icechunk.py
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2.0.0a0",
# ]
#
# [[tool.uv.index]]
# name = "scientific-python-nightly-wheels"
# url = "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple"
#
# [tool.uv]
# index-strategy = "unsafe-best-match"
#
# [tool.uv.sources]
# icechunk = { index = "scientific-python-nightly-wheels" }
# ///

import icechunk
import icechunk_v1

print(f"v1: {icechunk_v1.__version__}")
print(f"v2: {icechunk.__version__}")
```

```bash
third-wheel run test_icechunk.py \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
```

### Using download + rename manually

```bash
# 1. Download and rename v1 in one command (specify target Python version for uvx)
uvx third-wheel download icechunk \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    --version "<2" \
    --rename icechunk_v1 \
    --python-version 3.12 \
    -o ./wheels/

# 2. Download v2 wheel from nightly builds
uvx third-wheel download icechunk \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    --version ">=2.0.0.dev0" \
    --python-version 3.12 \
    -o ./wheels/

# 3. Create a venv and install both versions
uv venv
uv pip install ./wheels/icechunk_v1-*.whl  # v1 as icechunk_v1
uv pip install ./wheels/icechunk-2*.whl    # v2 as icechunk

# 4. Verify both work
uv run python -c "import icechunk_v1; print(f'v1: {icechunk_v1.__version__}')"
uv run python -c "import icechunk; print(f'v2: {icechunk.__version__}')"
```

**Optional: Inspect a wheel before renaming** to verify it uses underscore-prefix extensions:

```bash
uvx third-wheel inspect ./wheels/icechunk-*.whl
```

## Commands

### 🛞 run

Run a PEP 723 inline script with multi-version package support. This is the easiest way to use third-wheel — just annotate your script's dependencies and run it:

```python
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2",
# ]
# ///

import icechunk_v1  # old version
import icechunk     # new version

print(f"v1: {icechunk_v1.__version__}")
print(f"v2: {icechunk.__version__}")
```

```bash
third-wheel run script.py
```

The comment after a dependency (`# icechunk<2`) tells third-wheel to install `icechunk<2` from the index but rename the package to `icechunk_v1`. The script can then `import icechunk_v1`.

**Rename annotation syntax:**

| Annotation | Meaning |
|---|---|
| `"icechunk_v1",  # icechunk<2` | Install icechunk<2, rename to icechunk_v1 |
| `"zarr_v2",  # zarr>=2,<3` | Install zarr>=2,<3, rename to zarr_v2 |
| `"my_requests",  # requests` | Install requests (any version), rename to my_requests |

For more complex setups, use the structured `[tool.third-wheel]` form:

```python
# /// script
# dependencies = ["icechunk_v1", "icechunk>=2"]
# [tool.third-wheel]
# renames = [
#   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
# ]
# ///
```

If both the comment syntax and `[tool.third-wheel]` specify the same `new-name`, the structured form takes priority.

**Git/path sources** — build from a git repo or local path instead of downloading from an index:

```python
# /// script
# dependencies = ["zarr_dev", "zarr>=2.18,<3"]
# [tool.third-wheel]
# renames = [
#   {original = "zarr", new-name = "zarr_dev", source = "git+https://github.com/zarr-developers/zarr-python@main"},
# ]
# ///

import zarr_dev  # built from git main
import zarr      # released v2 from PyPI
```

The `source` field accepts:

- Git URLs: `git+https://github.com/org/repo@branch` (follows pip/uv convention)
- Local paths: `/path/to/project` or `./relative/path`

Git sources are cached by URL; local path sources always rebuild (since the source is mutable).

**CLI renames** override or supplement script annotations:

```bash
# Add a rename not in the script metadata
third-wheel run script.py --rename "icechunk<2=icechunk_v1"

# Use a custom index for renamed packages
third-wheel run script.py -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
```

The `--rename` format is `ORIGINAL[VERSION_SPEC]=NEW_NAME`.

**Argument passing:** Unknown flags are passed through to the script automatically. Use `--` if a script flag conflicts with a third-wheel flag:

```bash
# --my-flag goes to the script
third-wheel run script.py --my-flag value

# Explicit separator for ambiguous flags
third-wheel run script.py -- --rename "this-goes-to-script"
```

**Options:**

- `--rename`: Rename rule (can be specified multiple times)
- `-i, --index-url`: Package index URL for renamed packages (default: PyPI)
- `--python-version`: Target Python version (e.g., `3.12`)
- `-v, --verbose`: Print diagnostic info about what third-wheel is doing

### 🛞 sync

Install renamed packages into the current virtual environment. This is the project-level equivalent of `run` — instead of inline PEP 723 scripts, it reads rename specs from `pyproject.toml` and installs them via `uv pip install`.

**Quick start** — add a rename and install it in one step:

```bash
third-wheel add "icechunk<2=icechunk_v1" --sync
```

**pyproject.toml configuration** — declare renames in `[tool.third-wheel]`:

```toml
[tool.third-wheel]
renames = [
    {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
    {original = "zarr", new-name = "zarr_dev", source = "git+https://github.com/zarr-developers/zarr-python@main"},
]
```

The `source` field builds from a git URL or local path instead of downloading from the index.

> **Note:** Renamed packages should NOT be listed in `[project].dependencies` or
> `[dependency-groups]` — `uv sync` would fail trying to resolve them from PyPI.
> The `[tool.third-wheel]` section is ignored by uv. Run `third-wheel sync` to
> install them into your venv separately.

Then sync:

```bash
third-wheel sync
```

**CLI-only sync** (temporary, without modifying pyproject.toml):

```bash
third-wheel sync --rename "icechunk<2=icechunk_v1"
```

**Local wheels** via `--find-links` for CI or local builds:

```bash
third-wheel sync --find-links ./dist/ --rename "mypkg<2=mypkg_v1"
```

**The icechunk CI pattern** — `sync` simplifies multi-step workflows:

Before (2 steps):

```bash
third-wheel download icechunk --version ">=1,<2" --rename icechunk_v1 -o ./dist-v1/
uv pip install dist-v1/icechunk_v1-*.whl
```

After (1 step):

```bash
third-wheel sync --rename "icechunk>=1,<2=icechunk_v1"
```

**Options:**

- `--rename`: Rename rule (can be specified multiple times, temporary — not saved to pyproject.toml)
- `-i, --index-url`: Package index URL (default: PyPI, or `index-url` from `[tool.third-wheel]`)
- `--find-links`: Local directory containing pre-built wheels (skips downloading from index)
- `--force`: Force re-download even when wheels are already cached
- `--installer`: Installer backend to use: `uv` (default), `pip`, or `auto`. With `auto`, pixi/conda environments use `uv pip install --python <conda_python>` instead of plain pip.
- `--python-version`: Target Python version (e.g., `3.12`)
- `-p, --pyproject`: Path to pyproject.toml (default: auto-detect)
- `-v, --verbose`: Print diagnostic info

### 🛞 add

Add a rename to `pyproject.toml`'s `[tool.third-wheel]` section, or to a PEP 723 inline script with `--script`. Optionally install it immediately with `--sync`.

```bash
third-wheel add <rename_spec> [--source <url>] [--sync] [-i <index_url>] [-p <pyproject>]
third-wheel add --script <script.py> <rename_spec>

# Examples:
third-wheel add "icechunk<2=icechunk_v1"
third-wheel add "icechunk<2=icechunk_v1" --sync
third-wheel add "icechunk<2=icechunk_v1" -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
third-wheel add --script compare.py "pandas<2=pandas_v2"

# Build from git instead of downloading from an index:
third-wheel add "zarr=zarr_dev" --source "git+https://github.com/zarr-developers/zarr-python@main"
```

The `RENAME_SPEC` format is `ORIGINAL[VERSION_SPEC]=NEW_NAME` (same as `--rename` elsewhere).

For **pyproject.toml**: if `[tool.third-wheel]` doesn't exist, it is created. If a rename with the same `new-name` already exists, it is updated in place.

For **scripts**: the dependency is added to the `dependencies` list and a `[tool.third-wheel]` renames entry is added inside the `# /// script` metadata block.

**Options:**

- `--source`: Git URL or local path to build from instead of downloading (e.g., `git+https://github.com/org/repo@tag`)
- `--sync/--no-sync`: Also run `third-wheel sync` after adding (default: no)
- `--script`: Add to a PEP 723 inline script instead of pyproject.toml
- `-i, --index-url`: Package index URL to store in config
- `-p, --pyproject`: Path to pyproject.toml (default: `./pyproject.toml`)
- `-v, --verbose`: Print diagnostic info

### 🛞 cache-clean

Remove cached wheels used by `sync` and `run`. Useful when you want to force a fresh download or reclaim disk space.

```bash
third-wheel cache-clean              # Remove all cached wheels
third-wheel cache-clean --sync-only  # Remove only sync cache
third-wheel cache-clean --run-only   # Remove only run cache
third-wheel cache-clean -v           # Print what is being removed
```

**Options:**

- `--sync-only`: Only remove cached wheels from `sync` operations
- `--run-only`: Only remove cached wheels from `run` operations
- `-v, --verbose`: Print diagnostic info about what is being removed

### Real-world example: icechunk cross-version testing

The [icechunk](https://github.com/earth-mover/icechunk) project needs to run stateful
tests that verify v1-created data can be read by v2. Here's how to set that up locally
using `third-wheel sync`:

**One-time setup** (adds config to pyproject.toml, committed to the repo):

```bash
cd icechunk-python

# Add the rename spec to pyproject.toml
third-wheel add "icechunk>=1,<2=icechunk_v1"
```

This adds to `pyproject.toml`:

```toml
[tool.third-wheel]
renames = [
    {original = "icechunk", new-name = "icechunk_v1", version = ">=1,<2"},
]
```

**Daily development workflow:**

```bash
uv sync --group test      # install icechunk v2 (from source) + test deps
third-wheel sync           # download icechunk v1 from PyPI, rename, install
uv run pytest tests/test_stateful_compat.py -v
```

**In CI** (e.g., GitHub Actions):

```yaml
- name: Install icechunk + icechunk_v1
  run: |
    uv sync --group test
    uvx third-wheel sync --rename "icechunk>=1,<2=icechunk_v1"
```

Or if you have locally-built wheels:

```bash
third-wheel sync --find-links ./dist-v1/ --rename "icechunk>=1,<2=icechunk_v1"
```

**pixi-based workflow:**

icechunk also supports pixi. `third-wheel sync` auto-detects pixi/conda
environments. With `--installer auto` (or when auto-detected), it uses
`uv pip install --python <conda_python>` to install into the conda environment:

```bash
pixi install
pixi run third-wheel sync    # auto-detects pixi, uses uv pip install --python ...
```

Or be explicit with `--installer`:

```bash
pixi run third-wheel sync --installer pip   # use plain pip
pixi run third-wheel sync --installer auto  # use uv pip install --python <conda_python>
```

**Using both versions in tests:**

```python
import icechunk        # v2 (from source / latest)
import icechunk_v1     # v1 (downloaded + renamed)

# Create data with v1 API
v1_store = icechunk_v1.IcechunkStore.create(...)
# Read it back with v2 API
v2_store = icechunk.IcechunkStore.open(...)
```

### 🛞 rename

Rename a wheel package:

```bash
third-wheel rename <wheel_path> <new_name> [-o <output_dir>]

# Examples:
third-wheel rename icechunk-1.0.0-cp312-cp312-linux_x86_64.whl icechunk_v1
third-wheel rename ./downloads/pkg.whl my_pkg_old -o ./renamed/
```

**Options:**

- `-o, --output`: Output directory (default: same as input)
- `--no-update-imports`: Don't update import statements in Python files

### 🛞 download

Download a compatible wheel from a package index:

```bash
third-wheel download <package> [-o <output_dir>] [-i <index_url>] [--version <spec>] [--rename <new_name>]

# Examples:
third-wheel download numpy -o ./wheels/
third-wheel download icechunk -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
third-wheel download requests --version ">=2.0,<3"
third-wheel download icechunk --version "<2" -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

# Download and rename in one command:
third-wheel download icechunk --version "<2" --rename icechunk_v1 -o ./wheels/ \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
```

**Options:**

- `-o, --output`: Output directory (default: current directory)
- `-i, --index-url`: Package index URL (default: PyPI)
- `--version`: PEP 440 version specifier (e.g., `==1.0.0`, `<2`, `>=1.0,<2`)
- `--list`: List available wheels without downloading
- `--rename`: Rename the downloaded wheel to this package name (combines download + rename)
- `--python-version`: Target Python version (e.g., `3.12`). Useful with `uvx` to download wheels for a different Python than the one running third-wheel.

### 🔧 inspect

Inspect a wheel's structure before renaming:

```bash
third-wheel inspect <wheel_path> [--json]

# Example output:
# Wheel: icechunk-1.1.14-cp312-cp312-macosx_11_0_arm64.whl
# Distribution: icechunk
# Version: 1.1.14
#
# Compiled extensions (1):
#   - icechunk/_icechunk_python.cpython-312-darwin.so (underscore prefix - renamable)
#
# This wheel uses underscore-prefix extensions.
# Renaming should work correctly.
```

### 🛞 serve

Start a PEP 503 proxy server that renames packages on-the-fly:

```bash
# Install with server extras
pip install third-wheel[server]

# Start proxy with CLI options
third-wheel serve \
    -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    -r "icechunk=icechunk_v1:<2" \
    --port 8000

# Or use a config file
third-wheel serve -c proxy.toml
```

**Options:**

- `-c, --config`: Path to TOML config file
- `-u, --upstream`: Upstream index URL (can be specified multiple times)
- `-r, --rename`: Rename rule in format `original=new_name[:version_spec]`
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to listen on (default: 8000)

**Config file format (proxy.toml):**

```toml
[proxy]
host = "127.0.0.1"
port = 8000

[[proxy.upstreams]]
url = "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple/"

[renames]
icechunk = { name = "icechunk_v1", version = "<2" }
```

**Using with uv:**

```bash
# Start the proxy
third-wheel serve -u https://pypi.org/simple/ -r "requests=requests_old:<2"

# In another terminal, install from the proxy
uv pip install requests_old --index-url http://127.0.0.1:8000/simple/
```

The proxy:

1. Lists virtual packages (renamed packages) at `/simple/`
2. Fetches the original package from upstream when requested
3. Filters by version constraint if specified
4. Renames the wheel on-the-fly during download
5. Serves the renamed wheel to the client

## 🔧 How It Works

1. **Extracts** the wheel (which is a ZIP file)
2. **Renames** the package directory (`pkg/` → `pkg_v1/`)
3. **Renames** the `.dist-info` directory
4. **Updates METADATA** with the new package name
5. **Updates imports** in all Python files (`from pkg import` → `from pkg_v1 import`)
6. **Regenerates RECORD** with new file paths and SHA256 hashes
7. **Repacks** as a new wheel with the renamed filename

## 🔧 Compiled Extensions

For wheels with compiled extensions (`.so`/`.pyd` files), renaming works **only if** the extension uses an underscore-prefix naming pattern:

| Pattern | Example | Renamable? |
|---------|---------|------------|
| `_modulename.cpython-*.so` | `_icechunk_python.cpython-312-darwin.so` | Yes |
| `modulename.cpython-*.so` | `icechunk.cpython-312-darwin.so` | No |

### Why underscore prefix matters

Python's import system requires the `PyInit_<name>` function inside the `.so` file to match the filename. When you have `_mymodule.cpython-*.so`:

- Python looks for `PyInit__mymodule` (matches!)
- The parent package directory can be renamed freely
- `from newpkg._mymodule import ...` works because the `.so` name is unchanged

If the extension doesn't use the underscore prefix pattern, the tool will warn you and you should rebuild from source instead.

## Limitations

- **Wheels only**: third-wheel can only rename wheel (`.whl`) files, not sdists. If a package version only has sdists on PyPI (no wheels), it cannot be downloaded or renamed. Most modern packages publish wheels, but very old versions may not.
- **Compiled extensions without underscore prefix**: Cannot be renamed without rebuilding
- **Hardcoded package names in strings**: Not automatically updated (only import statements are). Packages that reference their own module paths as strings (config registries, plugin systems, `importlib.import_module()` calls) may break after renaming. For example, zarr internally references `"zarr.core.codec_pipeline.BatchedCodecPipeline"` — after renaming to `zarr_old`, this string won't resolve. Consider using `third-wheel patch` to fix internal references if needed.
- **Entry points**: Updated in metadata but external scripts may need adjustment
- **Import name ≠ package name**: Some packages have a different import name than their PyPI name (e.g., `scikit-image` is imported as `skimage`, `Pillow` as `PIL`, `opencv-python` as `cv2`). When renaming these, use the **import name** as the basis for the new name — third-wheel renames the directory inside the wheel, which matches the import name. For example, to rename `scikit-image`, use `skimage_old` (not `scikit_image_old`):

  ```python
  # dependencies = [
  #   "skimage_old",  # scikit-image>=0.24,<0.25
  #   "scikit-image>=0.26",
  # ]
  import skimage_old  # old version
  import skimage       # new version
  ```

## Development

```bash
# Clone and setup
git clone <repo>
cd third-wheel
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check src tests
uv run ruff format src tests
```

## License

BSD-3-Clause
