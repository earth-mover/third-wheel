# Planning

Cross-session communication channel for AI agents working on third-wheel. Check this file at the start of every session to understand current priorities, recent decisions, and notes from previous sessions.

## Current Priorities

From comprehensive 4-agent review (2026-03-10), ordered by severity:

1. **CRITICAL: XSS in `server/html.py`** — User-controlled values (project names, URLs, requires_python) embedded in HTML without `html.escape()`. Quick fix.
2. **CRITICAL: UnicodeDecodeError in rename.py and patch.py** — `.decode("utf-8")` on `.py` files with no error handling. Crashes on non-UTF8 files.
3. **HIGH: Fragile wheel name cache check** (`run.py:408`, `sync.py:247`) — `w.name.split("-")[0]` breaks for normalized multi-dash distribution names.
4. **HIGH: Broad `except Exception`** in `run.py:138` and `upstream.py:98` — catches SystemExit/KeyboardInterrupt.
5. **HIGH: Swallowed HTTP errors** in `upstream.py:76` — all upstream errors silently treated as 404.
6. **HIGH: Fragile filename rewriting** in `stream.py` — naive `split("-")` instead of `parse_wheel_filename()`.
7. **HIGH: METADATA not patched** in `patch.py` — Requires-Dist entries not updated when patching.
8. **HIGH: `serve` command missing from README** — no user-facing documentation.
9. **MEDIUM: Type annotations** in `_find_package_dir` — pyright errors from untyped set.
10. **MEDIUM: `_find_package_dir` misses namespace packages** — Only detects packages with `__init__.py`.
11. **TEST: `run_script` has zero unit tests** — Core orchestration function, highest-priority testing gap.
12. **TEST: Missing server passthrough endpoint tests**
13. **DOCS: `sync.py` functions missing from architecture.md, `test_sync.py` missing from testing.md**

## Decisions Log

Record architectural decisions here with date, context, and rationale so future sessions understand why things are the way they are.

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-10 | Extracted `_rename_wheel_files()` shared helper | Eliminated code duplication between `rename_wheel` and `rename_wheel_from_bytes` |
| 2026-03-10 | `rename_wheel_from_bytes` raises `ValueError` on malformed dist-info | Silent fallback was hiding real problems; fail-fast is safer |
| 2026-03-10 | `parse_wheel_filename` counts tags from end | Python/abi/platform are always the last 3 parts; counting from start broke on names with hyphens |
| 2026-03-10 | `sync` and `run` share caching infra from `run.py` | Avoids duplication; both need the same download-rename-cache workflow |
| 2026-03-10 | Internal docs split into `INTERNAL_DOCS/` directory | Keeps CLAUDE.md and AGENTS.md concise; detailed reference lives in topic-specific files |

## Session Notes

Leave notes here for the next session. Newest entries at the top.

### 2026-03-10 — Comprehensive 4-agent review complete

- Dispatched 4 parallel review agents: core modules, orchestration+CLI, server, docs+test infra.
- Found 13 prioritized issues (see Current Priorities above).
- Critical: XSS in html.py, UnicodeDecodeError in rename/patch.
- High: fragile cache name check, broad exception handlers, missing README docs.
- Starting fixes on a new branch.

### 2026-03-10 — Tech debt PR merged, v0.2.0 released

- Merged PR #10 (fix/rename-tech-debt) into main: parse_wheel_filename fix, shared helper extraction, inspect bools, XDG cache, 17 new tests.
- Merged PR #9 (sync/add/cache-clean commands) earlier in the session.
- Released v0.2.0 via GitHub Release (triggers PyPI publish).
- Restructured docs: AGENTS.md is now high-level rules linking to CLAUDE.md. Detailed docs in INTERNAL_DOCS/.
- Next session should tackle the two remaining open items below.

### 2026-03-10 — Documentation reorganization

- Reviewed and organized all `INTERNAL_DOCS/` files for consistency (headings, descriptions, no duplication).
- Created this planning doc as a cross-session communication channel.
- Updated AGENTS.md and CLAUDE.md to reference this file.
- All known-issues items from the sync feature work are resolved. Only namespace packages and `run_script` tests remain open.

## Conventions

- **Date format:** YYYY-MM-DD
- **Session notes:** Add new entries at the top with a `### DATE — Brief title` heading
- **Priorities:** Keep this list short (3-5 items). Move completed items to known-issues.md.
- **Decisions:** Only record non-obvious decisions. If the "why" is self-evident, it doesn't need an entry.
