# Useful Commands

Quick reference for common CLI commands used during development and testing.

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

# Add a rename to a PEP 723 script
uv run third-wheel add --script myscript.py "icechunk<2=icechunk_v1"

# Clean all cached wheels
uv run third-wheel cache-clean

# Clean only sync or run caches
uv run third-wheel cache-clean --sync-only
uv run third-wheel cache-clean --run-only
```

## Adding a New CLI Command

1. Add function in `cli.py` with `@main.command()` decorator
2. Use Click options/arguments
3. Use `console.print()` for output, `err_console.print()` for errors
4. Handle exceptions and call `sys.exit(1)` on error
