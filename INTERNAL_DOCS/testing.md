# Testing

Test organization, fixtures, and patterns used across the test suite.

## Running Tests

```bash
uv run python -m pytest tests/           # All tests
uv run python -m pytest tests/test_rename.py  # Unit tests only
uv run python -m pytest -m integration   # Integration tests (slower, network)
```

## Test File Locations

- Property-based tests: `test_properties.py` (Hypothesis)
- Unit tests: `test_rename.py`
- Tag/download tests: `test_download.py`
- Run/metadata parsing tests: `test_run.py`
- Patch tests: `test_patch.py`
- Server config tests: `test_config.py`
- Server endpoint tests: `test_server.py`
- Import rewriting tests: `test_integration.py`
- Multi-package isolation tests: `test_dual_install.py`
- Sync/add tests: `test_sync.py` (use the self-referential pattern — third-wheel can rename its own wheel — or the `--find-links` approach with locally-built test wheels)
- Real wheel tests: `test_icechunk_integration.py` with `@pytest.mark.integration`

## Dual-Install Tests

Tests create isolated venvs and install both original and renamed packages to verify:

1. Both packages import without errors
2. Module `__file__` paths are distinct
3. Internal import chains stay within each package
4. No `sys.modules` contamination
5. No leaked references to old package name in renamed package

## Property-Based Tests (Hypothesis)

`tests/test_properties.py` uses Hypothesis to test invariants and roundtrip properties:

```bash
uv run pytest tests/test_properties.py -v
```

53 property tests covering: name normalization, filename parse/build roundtrip, import rewriting, wheel rename roundtrip, PEP 723 parsing, CLI rename parsing, dependency patching, RECORD hashing, metadata updates, wheel tag parsing, rename merging, comment/TOML extraction, cache key generation, server config parsing/normalization/lookup, root/project HTML generation, and filename rewriting roundtrips.

Slow tests (`rename_wheel_from_bytes` roundtrips) use `max_examples=50` and `deadline=5000`.

## Test Wheel Creation

Use `conftest.create_test_wheel()` to create synthetic wheels with version-tagged functions:

```python
v1_wheel = create_test_wheel(tmp_path, "mypkg", "1.0.0")
v1_renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=tmp_path)
```
