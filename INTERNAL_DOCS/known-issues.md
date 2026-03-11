# Known Issues and Tech Debt

Tracker for bugs, tech debt, and missing test coverage. Mark items with `[x]` as they are fixed. Open items are also tracked in [planning.md](planning.md) under Current Priorities.

## Pre-existing (in main before sync feature)

- [x] **CRITICAL: `parse_wheel_filename` build tag heuristic** (`rename.py`) — Fixed: now counts from end (python/abi/platform are always last 3 parts).
- [x] **CRITICAL: `rename_wheel_from_bytes` version fallback** (`rename.py`) — Fixed: raises `ValueError` on malformed dist-info instead of silent fallback.
- [x] **HIGH: Code duplication rename_wheel vs rename_wheel_from_bytes** (`rename.py`) — Fixed: extracted `_rename_wheel_files()` shared helper.
- [ ] **MEDIUM: `_find_package_dir` misses namespace packages** (`rename.py`) — Only detects packages with `__init__.py`, missing PEP 420 implicit namespace packages.
- [x] **MEDIUM: `_has_server_extras()` is dead code** (`run.py:320-328`) — Never called. Removed.
- [x] **LOW: `inspect_wheel` stores booleans as strings** (`rename.py`) — Fixed: now uses proper booleans.
- [x] **TEST: `rename_wheel_from_bytes`** — Added `TestRenameWheelFromBytes` (5 tests).
- [x] **TEST: `inspect_wheel`** — Added `TestInspectWheel` (4 tests).
- [ ] **TEST: `run_script`** — Zero unit tests for core orchestration.

## New (introduced with sync feature)

- [x] **HIGH: `add_rename_to_pyproject` regex not section-scoped** (`sync.py`) — Fixed: regex searches now scoped to after `[tool.third-wheel]` header, bounded by next section.
- [x] **HIGH: `sync_cmd` silently ignores missing explicit `--pyproject`** (`cli.py`) — Fixed: errors when explicitly provided path doesn't exist.
- [x] **HIGH: `add_cmd --sync` drops options** (`cli.py`) — Fixed: now reads pyproject config for index-url (matching `sync_cmd` behavior).
- [x] **MEDIUM: `_detect_installer` no existence check** (`sync.py`) — Fixed: falls back to default `uv pip install` when neither conda python path exists.
- [x] **MEDIUM: `cache_clean_cmd` mutual exclusion check after early return** (`cli.py`) — Fixed: validation moved before cache existence check.
- [x] **MEDIUM: `get_pyproject_config` catches bare Exception** (`sync.py`) — Fixed: now catches only `TOMLDecodeError`.
- [x] **MEDIUM: `cache_dir()` ignores XDG_CACHE_HOME** (`run.py`) — Fixed: now respects `$XDG_CACHE_HOME`.
- [x] **LOW: Inconsistent error emoji across CLI commands** — Fixed: all commands now use `🔧 Error:`.
- [x] **LOW: `sync_cmd` source attribution wrong** (`cli.py`) — Fixed: checks `new_name` in CLI set instead of using dataclass `in`.
- [x] **TEST: `cache_dir()` env var override** — Added `TestCacheDir` (4 tests: default, env override, XDG, priority).
- [x] **TEST: `rename_cache_key()` stability** — Added `TestRenameCacheKey` (5 tests: stable, differs on version/index/python, order-independent).
- [x] **TEST: `parse_wheel_filename` invalid inputs** — Added `TestParseWheelFilenameEdgeCases` (3 tests).
- [x] **TEST: `rename_wheel(update_imports=False)`** — Added test in `TestRenameWheel`.

## Round 2 review (2026-03-10)

- [x] **CRITICAL: XSS in `server/html.py`** — Fixed: all user-controlled values now escaped with `html.escape()`.
- [x] **CRITICAL: UnicodeDecodeError in rename.py and patch.py** — Fixed: `.decode("utf-8")` now wrapped in try/except, skips non-UTF8 files.
- [x] **HIGH: Broad `except Exception` in `run.py`** — Fixed: now catches `(TOMLDecodeError, ValueError, KeyError)`.
- [x] **HIGH: Broad `except Exception` in `upstream.py`** — Fixed: now catches `(ValueError, TypeError)`.
- [x] **HIGH: Swallowed HTTP errors in `upstream.py`** — Fixed: now logs warnings via `logging`.
- [x] **HIGH: Fragile filename rewriting in `stream.py`** — Fixed: now uses `parse_wheel_filename()` from rename.py.
- [x] **MEDIUM: Type annotations in `_find_package_dir`** — Fixed: added explicit `set[str]` and `dict[str, int]` annotations.
- [ ] **MEDIUM: `_find_package_dir` misses namespace packages** — Needs research; uncommon in wheels.
- [ ] **MEDIUM: METADATA not patched in `patch.py`** — Requires-Dist entries not updated when patching.
- [ ] **HIGH: `serve` command missing from README** — No user-facing documentation for proxy server.
- [ ] **TEST: `run_script`** — Zero unit tests for core orchestration.
- [ ] **TEST: Missing server passthrough endpoint tests**
- [x] **HIGH: `parse_wheel_tags` build tag heuristic in download.py** — Same bug as the rename.py heuristic (used `parts[2][0].isdigit()` instead of counting from end). Fixed: now uses `parts[-3]`, `parts[-2]`, `parts[-1]`.
- [ ] **DOCS: `sync.py` functions missing from architecture.md, `test_sync.py` missing from testing.md**
