"""Sync renamed packages into a project's virtual environment.

Reads rename specifications from ``[tool.third-wheel]`` in pyproject.toml,
downloads and renames wheels, and installs them via ``uv pip install``.

Declare renames in pyproject.toml::

    [tool.third-wheel]
    renames = [
        {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
    ]

Important: renamed packages should NOT be listed in ``[project].dependencies``
or ``[dependency-groups]``.  Those sections are resolved by ``uv sync`` which
would fail trying to find them on PyPI.  The ``[tool.third-wheel]`` section is
ignored by uv — run ``third-wheel sync`` to install renamed packages separately.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from third_wheel.run import (
    RenameSpec,
    cache_dir,
    extract_renames_from_tool_table,
    prepare_wheels,
    rename_cache_key,
)


def parse_renames_from_pyproject(
    pyproject_path: Path,
) -> list[RenameSpec]:
    """Parse rename specs from a pyproject.toml file.

    Reads from ``[tool.third-wheel].renames``::

        [tool.third-wheel]
        renames = [
            {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
        ]

    Comment-style annotations (``"pkg_v1",  # pkg<2``) are NOT supported in
    pyproject.toml — too many false positives from ruff config, commented-out
    deps, etc.  Use ``[tool.third-wheel]`` exclusively.  Comment annotations
    remain available in PEP 723 inline scripts via ``third-wheel run``.

    Returns:
        List of RenameSpec from the ``[tool.third-wheel]`` section.
    """
    raw_text = pyproject_path.read_text()
    return extract_renames_from_tool_table(raw_text)


def get_pyproject_config(pyproject_path: Path) -> dict[str, str]:
    """Read optional config from [tool.third-wheel] in pyproject.toml.

    Currently supports:
        index-url: default package index URL
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        data: dict[str, object] = tomllib.loads(pyproject_path.read_text())
    except tomllib.TOMLDecodeError:
        return {}

    tool_section = data.get("tool")
    if not isinstance(tool_section, dict):
        return {}
    tw_section = tool_section.get("third-wheel")
    if not isinstance(tw_section, dict):
        return {}

    config: dict[str, str] = {}
    index_url = tw_section.get("index-url")
    if isinstance(index_url, str):
        config["index_url"] = index_url
    return config


def _find_wheel_in_directory(
    find_links: Path,
    original: str,
    version: str | None,
) -> Path | None:
    """Find a matching wheel in a local directory.

    Searches for wheels whose distribution name matches ``original``
    and optionally satisfies ``version``.

    Returns the best match (highest version), or None.
    """
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    from third_wheel.rename import normalize_name, parse_wheel_filename

    spec = SpecifierSet(version) if version else None
    normalized = normalize_name(original)

    candidates: list[tuple[Version, Path]] = []
    for whl in find_links.glob("*.whl"):
        try:
            info = parse_wheel_filename(whl.name)
        except ValueError:
            continue

        if normalize_name(info["distribution"]) != normalized:
            continue

        ver = Version(info["version"])
        if spec and ver not in spec:
            continue

        candidates.append((ver, whl))

    if not candidates:
        return None

    # Return the highest-version match
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def prepare_wheels_from_find_links(
    renames: list[RenameSpec],
    wheel_dir: Path,
    find_links: Path,
) -> None:
    """Rename wheels from a local directory instead of downloading.

    For each rename spec, finds a matching wheel in ``find_links``,
    copies and renames it into ``wheel_dir``.
    """
    from third_wheel.rename import rename_wheel

    for spec in renames:
        source = _find_wheel_in_directory(find_links, spec.original, spec.version)
        if source is None:
            raise RuntimeError(
                f"Could not find a wheel matching {spec.version_spec} in {find_links}"
            )

        # Copy to wheel_dir so we don't modify the source
        copied = wheel_dir / source.name
        shutil.copy2(source, copied)

        renamed = rename_wheel(copied, spec.new_name, output_dir=wheel_dir)
        # Remove the copy of the original
        if copied != renamed:
            copied.unlink()


def _detect_installer() -> list[str]:
    """Auto-detect the best installer command for the current environment.

    Returns the command prefix as a list.

    Detection logic:
    - If ``CONDA_PREFIX`` is set (pixi or conda), use
      ``uv pip install --python <conda_python>`` so that packages land in
      the conda/pixi environment even when third-wheel itself runs via uvx.
    - Otherwise, use plain ``uv pip install`` (the default for uv-managed
      projects).
    """
    import os

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        from pathlib import Path

        # Find the conda env's Python
        conda_python = Path(conda_prefix) / "bin" / "python"
        if not conda_python.exists():
            # Windows fallback
            conda_python = Path(conda_prefix) / "python.exe"
        if not conda_python.exists():
            # Neither path exists — fall back to default uv pip install
            return ["uv", "pip", "install"]
        return ["uv", "pip", "install", "--python", str(conda_python)]
    return ["uv", "pip", "install"]


def sync(
    renames: list[RenameSpec],
    *,
    index_url: str = "https://pypi.org/simple/",
    find_links: Path | None = None,
    python_version: str | None = None,
    installer: str | None = None,
    force: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Download, rename, and install wheels into the current virtual environment.

    Renamed wheels are cached in ``~/.cache/third-wheel/sync/`` keyed by the
    rename configuration (separate from ``third-wheel run``'s cache namespace).

    Args:
        renames: Rename specifications to process.
        index_url: PEP 503 package index URL (ignored when find_links is set).
        find_links: Local directory containing pre-built wheels.  When set,
            wheels are sourced from this directory instead of downloading.
        python_version: Target Python version (e.g. ``"3.12"``).
        installer: Installer to use: ``"uv"`` for ``uv pip install``,
            ``"pip"`` for ``pip install``, or ``None`` to auto-detect
            (uses ``uv pip install --python`` targeting pixi/conda envs
            when ``CONDA_PREFIX`` is set, plain ``uv pip install`` otherwise).
        force: If True, re-download and re-rename wheels even if cached.
        verbose: Print extra diagnostic info.

    Returns:
        List of installed wheel paths.
    """
    if not renames:
        return []

    # Cache key includes find_links path so local-dir syncs don't collide
    # with index syncs.
    cache_source = str(find_links) if find_links else index_url
    cache_key = rename_cache_key(renames, cache_source, python_version)
    cache = cache_dir() / "sync" / cache_key
    wheel_dir = cache / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        for spec in renames:
            ver = f"({spec.version})" if spec.version else ""
            print(
                f"third-wheel sync: {spec.original}{ver} -> {spec.new_name}",
                file=sys.stderr,
            )

    # Check if renamed wheels are already cached
    expected_names = {r.new_name.replace("-", "_") for r in renames}

    needs_prepare = force
    if not needs_prepare:
        existing_wheels = list(wheel_dir.glob("*.whl"))
        cached_names = {w.name.split("-")[0] for w in existing_wheels}
        needs_prepare = not expected_names.issubset(cached_names)

    if needs_prepare:
        if force:
            # Clear cached wheels so we get fresh ones
            for old_whl in wheel_dir.glob("*.whl"):
                old_whl.unlink()

        if verbose:
            source = find_links or index_url
            print(
                f"third-wheel sync: preparing wheels from {source}...",
                file=sys.stderr,
            )

        if find_links:
            prepare_wheels_from_find_links(renames, wheel_dir, find_links)
        else:
            prepare_wheels(renames, wheel_dir, index_url, python_version)
    elif verbose:
        print(
            f"third-wheel sync: using cached wheels from {wheel_dir}",
            file=sys.stderr,
        )

    # Determine install command
    if installer == "uv":
        install_cmd = ["uv", "pip", "install"]
    elif installer == "pip":
        install_cmd = [sys.executable, "-m", "pip", "install"]
    else:
        # Auto-detect: uses CONDA_PREFIX to target pixi/conda envs
        install_cmd = _detect_installer()

    # Collect renamed wheels and install them in a single batch
    renamed_wheels = [w for w in wheel_dir.glob("*.whl") if w.name.split("-")[0] in expected_names]

    if not renamed_wheels:
        return []

    if verbose:
        for wheel in renamed_wheels:
            print(
                f"third-wheel sync: installing {wheel.name}...",
                file=sys.stderr,
            )

    result = subprocess.run(
        [*install_cmd, *(str(w) for w in renamed_wheels)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        names = ", ".join(w.name for w in renamed_wheels)
        raise RuntimeError(f"Failed to install {names}: {result.stderr}")

    return renamed_wheels


# ---------------------------------------------------------------------------
# pyproject.toml modification helpers
# ---------------------------------------------------------------------------

# Pattern to find existing [tool.third-wheel] section (anchored to end of line)
_TOOL_SECTION_RE = re.compile(r"^\[tool\.third-wheel\]\s*$", re.MULTILINE)


def add_rename_to_pyproject(
    pyproject_path: Path,
    spec: RenameSpec,
) -> None:
    """Add or update a rename entry in pyproject.toml's ``[tool.third-wheel]`` section.

    If the section doesn't exist, it is created.  If a rename with the same
    ``new-name`` already exists, it is updated in place.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        spec: The rename specification to add.
    """
    content = pyproject_path.read_text()

    # Build the TOML entry for this rename
    version_part = f', version = "{spec.version}"' if spec.version else ""
    entry = f'{{original = "{spec.original}", new-name = "{spec.new_name}"{version_part}}}'

    m_section = _TOOL_SECTION_RE.search(content)
    if m_section:
        # Determine the extent of the [tool.third-wheel] section
        # (ends at the next [section] header or EOF)
        next_section = re.search(r"^\[", content[m_section.end() :], re.MULTILINE)
        section_end = m_section.end() + next_section.start() if next_section else len(content)
        section_text = content[m_section.end() : section_end]

        # Check if this new_name already exists within the section
        existing_pattern = re.compile(
            r'\{[^}]*new-name\s*=\s*"' + re.escape(spec.new_name) + r'"[^}]*\}',
        )
        existing_match = existing_pattern.search(section_text)
        if existing_match:
            # Replace the existing entry (adjust offset to full content)
            abs_start = m_section.end() + existing_match.start()
            abs_end = m_section.end() + existing_match.end()
            content = content[:abs_start] + entry + content[abs_end:]
        else:
            # Append to the renames list within the section
            renames_pattern = re.compile(
                r"(renames\s*=\s*\[)(.*?)(\])",
                re.DOTALL,
            )
            m = renames_pattern.search(section_text)
            if m:
                # Add the new entry before the closing ]
                existing_entries = m.group(2).rstrip()
                if existing_entries.rstrip().endswith(","):
                    separator = "\n    "
                elif existing_entries.strip():
                    separator = ",\n    "
                else:
                    separator = "\n    "
                new_entries = f"{existing_entries}{separator}{entry},\n"
                # Adjust offset to full content
                abs_start = m_section.end() + m.start(2)
                abs_end = m_section.end() + m.end(2)
                content = content[:abs_start] + new_entries + content[abs_end:]
            else:
                # Section exists but no renames key — add it
                insert_pos = m_section.end()
                content = (
                    content[:insert_pos]
                    + f"\nrenames = [\n    {entry},\n]\n"
                    + content[insert_pos:]
                )
    else:
        # No [tool.third-wheel] section — create it
        content = content.rstrip() + "\n\n[tool.third-wheel]\nrenames = [\n"
        content += f"    {entry},\n"
        content += "]\n"

    pyproject_path.write_text(content)
