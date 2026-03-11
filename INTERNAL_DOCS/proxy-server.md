# Proxy Server

Setup, configuration, and usage of the on-the-fly renaming proxy server.

The proxy server enables `uv sync` to install renamed packages without manual wheel downloading.

## How It Works

1. Start proxy: `third-wheel serve -u <upstream> -r "pkg=pkg_v1:<version>"`
2. Proxy serves `/simple/pkg_v1/` endpoint with renamed wheel links
3. When uv requests the wheel, proxy downloads from upstream, renames on-the-fly, serves renamed wheel
4. uv installs `pkg_v1` as a normal package

## Server Modules

- `config.py`: Loads TOML config or CLI args, handles PEP 503 name normalization
- `app.py`: FastAPI routes for `/simple/`, `/simple/{project}/`, `/simple/{project}/{filename}`
- `upstream.py`: Async client to fetch packages from upstream indexes
- `stream.py`: Downloads wheel, calls `rename_wheel_from_bytes()`, returns renamed bytes
- `html.py`: Generates PEP 503 HTML with rewritten filenames

## Configuration

```toml
[tool.uv]
extra-index-url = ["http://127.0.0.1:8123/simple/"]
prerelease = "allow"
index-strategy = "unsafe-best-match"  # Required for mixing indexes
resolution = "highest"
```

## Full Setup Example

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

### Step 4: Install and use

```bash
uv sync
```

```python
import icechunk      # v2
import icechunk_v1   # v1

# Both are fully isolated and functional
```

See `tests/fixtures/dual-install/` for a complete working example.
