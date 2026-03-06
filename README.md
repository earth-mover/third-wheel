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
# Use directly with uvx (recommended)
uvx third-wheel --help

# Or install globally
pip install third-wheel
```

## End-to-End Example: icechunk v1 + v2

Here's a complete example of setting up both icechunk versions for regression testing:

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
- **Hardcoded package names in strings**: Not automatically updated (only import statements are)
- **Entry points**: Updated in metadata but external scripts may need adjustment

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
