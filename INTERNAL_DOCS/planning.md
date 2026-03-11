# Planning

Cross-session communication channel for AI agents working on third-wheel. Check this file at the start of every session to understand current priorities, recent decisions, and notes from previous sessions.

## Current Priorities

Open items from [known-issues.md](known-issues.md), ordered by importance:

1. **MEDIUM: `_find_package_dir` misses namespace packages** (`rename.py`) — Only detects packages with `__init__.py`, missing PEP 420 implicit namespace packages. Needs research into how common namespace packages are in wheels and whether the current heuristic causes real failures.

2. **TEST: `run_script` has zero unit tests** — Core orchestration function in `run.py` has no unit test coverage. This is the highest-priority testing gap. Consider mocking `subprocess` and `download_compatible_wheel` to test the orchestration logic without network access.

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
