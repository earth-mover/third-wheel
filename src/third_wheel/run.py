"""Run PEP 723 inline scripts with third-wheel rename support.

Parses inline script metadata, detects rename annotations, and orchestrates
downloading/renaming wheels before delegating to `uv run`.

Rename annotations can be specified in two ways:

1. Comment syntax (inline with dependency):
       "icechunk_v1",  # icechunk<2

2. Structured metadata:
       [tool.third-wheel]
       renames = [
           {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
       ]
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenameSpec:
    """A rename specification: install `original` with `version` constraint, rename to `new_name`."""

    original: str
    new_name: str
    version: str | None = None

    @property
    def version_spec(self) -> str:
        """Full PEP 440 specifier string for the original package."""
        if self.version:
            return f"{self.original}{self.version}"
        return self.original


def parse_pep723_metadata(script: str) -> str | None:
    """Extract PEP 723 inline metadata block from a script.

    Returns the raw TOML string between ``# /// script`` and ``# ///`` markers,
    or None if no metadata block is found.
    """
    lines = script.splitlines()
    in_block = False
    toml_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "# /// script":
            in_block = True
            continue
        if stripped == "# ///" and in_block:
            break
        if in_block:
            # Strip leading "# " prefix (PEP 723 format)
            if stripped.startswith("# "):
                toml_lines.append(stripped[2:])
            elif stripped == "#":
                toml_lines.append("")
            else:
                # Not a valid metadata line — stop
                break

    if not toml_lines:
        return None
    return "\n".join(toml_lines)


# Pattern for comment-style rename annotations in dependency lines.
# Matches: "icechunk_v1",  # icechunk<2
#          "icechunk_v1",  # icechunk < 2
#          "icechunk_v1"  # icechunk>=1.0,<2
_RENAME_COMMENT_RE = re.compile(
    r"""
    ^["']                          # opening quote
    (?P<new_name>[a-zA-Z0-9_-]+)   # the new (renamed) package name
    ["']                           # closing quote
    \s*,?\s*                       # optional comma and whitespace
    \#\s*                          # comment marker
    (?P<original>[a-zA-Z0-9_-]+)   # original package name
    \s*
    (?P<version>[<>=!~].*)?        # optional version specifier
    $
    """,
    re.VERBOSE,
)


def extract_renames_from_comments(toml_str: str) -> list[RenameSpec]:
    """Extract rename specs from comment annotations in the dependencies list.

    Scans the raw TOML string for lines like:
        "icechunk_v1",  # icechunk<2

    Returns a list of RenameSpec for each annotated dependency.
    """
    renames: list[RenameSpec] = []
    for line in toml_str.splitlines():
        stripped = line.strip()
        m = _RENAME_COMMENT_RE.match(stripped)
        if m:
            version = m.group("version")
            if version:
                version = version.strip().rstrip(",")
            renames.append(
                RenameSpec(
                    original=m.group("original"),
                    new_name=m.group("new_name"),
                    version=version or None,
                )
            )
    return renames


def extract_renames_from_tool_table(toml_str: str) -> list[RenameSpec]:
    """Extract rename specs from [tool.third-wheel] metadata.

    Looks for:
        [tool.third-wheel]
        renames = [
            {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
        ]
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        data = tomllib.loads(toml_str)
    except Exception:
        return []

    tool_config = data.get("tool", {}).get("third-wheel", {})
    rename_list = tool_config.get("renames", [])

    renames: list[RenameSpec] = []
    for entry in rename_list:
        if isinstance(entry, dict) and "original" in entry and "new-name" in entry:
            renames.append(
                RenameSpec(
                    original=entry["original"],
                    new_name=entry["new-name"],
                    version=entry.get("version"),
                )
            )
    return renames


def parse_all_renames(script: str) -> list[RenameSpec]:
    """Parse all rename specs from a script's inline metadata.

    Merges comment-style and [tool.third-wheel] renames.
    If both specify the same new_name, the structured form wins.
    """
    toml_str = parse_pep723_metadata(script)
    if toml_str is None:
        return []

    comment_renames = extract_renames_from_comments(toml_str)
    tool_renames = extract_renames_from_tool_table(toml_str)

    # tool.third-wheel renames take priority — deduplicate by new_name
    seen = {r.new_name for r in tool_renames}
    merged = list(tool_renames)
    for r in comment_renames:
        if r.new_name not in seen:
            merged.append(r)
            seen.add(r.new_name)

    return merged


def parse_cli_renames(rename_args: tuple[str, ...] | list[str]) -> list[RenameSpec]:
    """Parse --rename CLI arguments.

    Format: "icechunk<2=icechunk_v1" or "icechunk=icechunk_v1"
    (original[version_spec]=new_name)

    Splits on the *last* ``=`` to avoid ambiguity with version specifiers
    that contain ``=`` (e.g., ``>=2.0``).
    """
    pkg_re = re.compile(r"^(?P<original>[a-zA-Z0-9_-]+)(?P<version>[<>=!~].+)?$")
    name_re = re.compile(r"^[a-zA-Z0-9_-]+$")

    renames: list[RenameSpec] = []
    for arg in rename_args:
        # Split on the last '='
        idx = arg.rfind("=")
        if idx <= 0:
            raise ValueError(
                f"Invalid --rename format: {arg!r}. "
                f"Expected: 'package[version_spec]=new_name' (e.g., 'icechunk<2=icechunk_v1')"
            )

        lhs = arg[:idx]
        new_name = arg[idx + 1 :]

        if not name_re.match(new_name):
            raise ValueError(
                f"Invalid new name in --rename: {new_name!r}. Must be a valid Python package name."
            )

        m = pkg_re.match(lhs)
        if not m:
            raise ValueError(
                f"Invalid --rename format: {arg!r}. "
                f"Expected: 'package[version_spec]=new_name' (e.g., 'icechunk<2=icechunk_v1')"
            )

        renames.append(
            RenameSpec(
                original=m.group("original"),
                new_name=new_name,
                version=m.group("version") or None,
            )
        )
    return renames


def merge_renames(
    script_renames: list[RenameSpec],
    cli_renames: list[RenameSpec],
) -> list[RenameSpec]:
    """Merge script and CLI renames. CLI renames override script renames by new_name."""
    seen = {r.new_name for r in cli_renames}
    merged = list(cli_renames)
    for r in script_renames:
        if r.new_name not in seen:
            merged.append(r)
            seen.add(r.new_name)
    return merged


def rewrite_script_metadata(script: str, renames: list[RenameSpec]) -> str:
    """Rewrite the script to remove rename comments from dependencies.

    This produces a clean script where renamed deps are just plain package names,
    suitable for passing to uv (which will find them via --find-links).
    """
    rename_new_names = {r.new_name for r in renames}
    lines = script.splitlines(keepends=True)
    result: list[str] = []

    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped == "# /// script":
            in_block = True
            result.append(line)
            continue
        if stripped == "# ///" and in_block:
            in_block = False
            result.append(line)
            continue

        if in_block:
            # Check if this line has a rename comment — strip the comment part
            content = stripped
            if content.startswith("# "):
                content = content[2:]

            m = _RENAME_COMMENT_RE.match(content.strip())
            if m and m.group("new_name") in rename_new_names:
                # Keep just the dependency, drop the comment
                # Reconstruct: #   "new_name",
                indent = line[: len(line) - len(line.lstrip())]
                new_name = m.group("new_name")
                result.append(f'{indent}#   "{new_name}",\n')
                continue

        result.append(line)

    return "".join(result)


def prepare_wheels(
    renames: list[RenameSpec],
    wheel_dir: Path,
    index_url: str,
    python_version: str | None,
) -> None:
    """Download and rename wheels for all rename specs.

    Args:
        renames: Rename specifications
        wheel_dir: Directory to place renamed wheels
        index_url: Package index URL
        python_version: Target Python version
    """
    from third_wheel.download import download_compatible_wheel
    from third_wheel.rename import rename_wheel

    for spec in renames:
        downloaded = download_compatible_wheel(
            spec.original,
            wheel_dir,
            index_url=index_url,
            version=spec.version,
            python_version=python_version,
            show_progress=False,
        )
        if downloaded is None:
            raise RuntimeError(f"Could not find a compatible wheel for {spec.version_spec}")

        renamed = rename_wheel(downloaded, spec.new_name, output_dir=wheel_dir)
        # Remove the original (un-renamed) wheel
        if downloaded != renamed:
            downloaded.unlink()


def cache_dir() -> Path:
    """Return the third-wheel cache directory.

    Priority: $THIRD_WHEEL_CACHE_DIR > $XDG_CACHE_HOME/third-wheel > ~/.cache/third-wheel.
    """
    env = os.environ.get("THIRD_WHEEL_CACHE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "third-wheel"
    return Path.home() / ".cache" / "third-wheel"


def rename_cache_key(
    renames: list[RenameSpec],
    index_url: str,
    python_version: str | None,
) -> str:
    """Compute a stable hash for a set of rename specs.

    The hash changes when the renames, index URL, or python version change,
    so different configurations get separate cache dirs.
    """
    parts = []
    for r in sorted(renames, key=lambda r: r.new_name):
        parts.append(f"{r.original}|{r.version or ''}|{r.new_name}")
    parts.append(f"index={index_url}")
    parts.append(f"python={python_version or 'auto'}")
    key_str = "\n".join(parts)
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def run_script(
    script_path: Path,
    cli_renames: list[RenameSpec] | None = None,
    index_url: str = "https://pypi.org/simple/",
    python_version: str | None = None,
    script_args: list[str] | None = None,
    verbose: bool = False,
) -> int:
    """Run a PEP 723 script with third-wheel rename support.

    Renamed wheels are cached in ~/.cache/third-wheel/ (or $THIRD_WHEEL_CACHE_DIR)
    keyed by the rename configuration. Subsequent runs with the same renames skip
    the download+rename step entirely.

    Args:
        script_path: Path to the script
        cli_renames: Rename specs from CLI --rename args
        index_url: Package index for renamed packages
        python_version: Target Python version
        script_args: Arguments to pass to the script
        verbose: Print extra info

    Returns:
        Exit code from the script
    """
    script_text = script_path.read_text()
    script_renames = parse_all_renames(script_text)
    all_renames = merge_renames(script_renames, cli_renames or [])

    if not all_renames:
        # No renames needed — just delegate to uv run directly
        cmd = ["uv", "run", str(script_path)]
        if script_args:
            cmd.extend(script_args)
        result = subprocess.run(cmd)
        return result.returncode

    # Use a stable cache directory keyed by the rename configuration.
    # This avoids re-downloading and re-renaming wheels on every run.
    cache_key = rename_cache_key(all_renames, index_url, python_version)
    cache = cache_dir() / cache_key
    wheel_dir = cache / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        for spec in all_renames:
            print(
                f"third-wheel: {spec.original}"
                f"{'(' + spec.version + ')' if spec.version else ''}"
                f" -> {spec.new_name}",
                file=sys.stderr,
            )

    # Check if renamed wheels are already cached
    existing_wheels = list(wheel_dir.glob("*.whl"))
    expected_names = {r.new_name.replace("-", "_") for r in all_renames}
    cached_names = {w.name.split("-")[0] for w in existing_wheels}

    if not expected_names.issubset(cached_names):
        if verbose:
            print("third-wheel: downloading and renaming wheels...", file=sys.stderr)
        prepare_wheels(
            all_renames,
            wheel_dir,
            index_url=index_url,
            python_version=python_version,
        )
    elif verbose:
        print(f"third-wheel: using cached wheels from {wheel_dir}", file=sys.stderr)

    # Write the cleaned-up script to the cache dir (stable path for uv caching)
    clean_script = rewrite_script_metadata(script_text, all_renames)
    cached_script = cache / script_path.name
    cached_script.write_text(clean_script)

    # Build uv run command
    # --find-links points uv at our pre-downloaded renamed wheels
    cmd = [
        "uv",
        "run",
        "--find-links",
        str(wheel_dir),
        str(cached_script),
    ]
    if script_args:
        cmd.extend(script_args)

    if verbose:
        print(f"third-wheel: running: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd)
    return result.returncode
