"""Build wheels from git URLs or local paths.

Uses ``uv pip wheel`` to build a single wheel from a git or local path source,
then returns the path to the built wheel.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def build_wheel_from_source(
    source: str,
    output_dir: Path,
    python_version: str | None = None,  # noqa: ARG001
) -> Path | None:
    """Build a wheel from a git URL or local path.

    Args:
        source: A git URL (``git+https://...@ref``) or a local filesystem path.
        output_dir: Directory to write the built wheel into.
        python_version: Optional Python version constraint (currently unused but
            reserved for future ``--python-version`` passthrough).

    Returns:
        Path to the built wheel, or None if the build produced no wheel.

    Raises:
        RuntimeError: If the build command fails.
    """
    # Remove any existing wheels so we can identify the newly built one
    before = set(output_dir.glob("*.whl"))

    cmd = [
        "uv",
        "pip",
        "wheel",
        source,
        "--no-deps",
        "--wheel-dir",
        str(output_dir),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to build wheel from {source}:\n{result.stderr.strip()}")

    # Find the newly created wheel
    after = set(output_dir.glob("*.whl"))
    new_wheels = after - before

    if not new_wheels:
        # Log stderr for debugging but don't crash
        print(
            f"third-wheel: warning: uv pip wheel succeeded but no new .whl found\n"
            f"  stdout: {result.stdout.strip()}\n"
            f"  stderr: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return None

    # If multiple wheels were produced (shouldn't happen with --no-deps),
    # return the first one.
    return next(iter(sorted(new_wheels)))
