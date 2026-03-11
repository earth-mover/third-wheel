"""Download wheels from PEP 503 compatible package indexes.

This module provides functionality to download wheels from package indexes
like PyPI or Anaconda.org without requiring pip to be installed.

Uses pypi-simple for PEP 503 parsing and packaging.tags for platform matching.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet
from packaging.tags import Tag, compatible_tags, cpython_tags, sys_tags
from packaging.version import Version
from pypi_simple import PyPISimple

if TYPE_CHECKING:
    from pathlib import Path

    from pypi_simple import DistributionPackage


def get_compatible_tags(python_version: str | None = None) -> list[Tag]:
    """Get ordered list of compatible tags for current platform.

    Args:
        python_version: Optional Python version string (e.g., "3.12", "3.11").
                       If None, uses the current interpreter's version.
    """
    if python_version is None:
        return list(sys_tags())

    # Parse version string like "3.12" -> (3, 12)
    parts = python_version.split(".")
    if len(parts) < 2:
        raise ValueError(f"Invalid Python version: {python_version}. Expected format: 3.12")
    major, minor = int(parts[0]), int(parts[1])
    py_version = (major, minor)

    # Generate CPython tags for the specified version
    # We need to combine cpython_tags (for cp312-cp312-*) and compatible_tags (for py3-none-*)
    tags: list[Tag] = []
    tags.extend(cpython_tags(python_version=py_version))
    tags.extend(compatible_tags(python_version=py_version))
    return tags


def parse_wheel_tags(filename: str) -> list[Tag]:
    """Extract platform tags from a wheel filename."""
    # Format: {dist}-{ver}(-{build})?-{py}-{abi}-{plat}.whl
    name = filename[:-4]  # Remove .whl
    parts = name.split("-")

    if len(parts) < 5:
        return []

    # Last 3 parts are always python-abi-platform (count from end to handle
    # build tags and distribution names with hyphens correctly)
    py_tags = parts[-3].split(".")
    abi_tags = parts[-2].split(".")
    plat_tags = parts[-1].split(".")
    return [Tag(py, abi, plat) for py in py_tags for abi in abi_tags for plat in plat_tags]


def best_wheel(
    packages: list[DistributionPackage],
    compatible_tags: list[Tag] | None = None,
) -> DistributionPackage | None:
    """Find the best compatible wheel (highest version, most specific tag)."""
    if compatible_tags is None:
        compatible_tags = get_compatible_tags()

    # Create tag priority map (lower index = higher priority)
    tag_priority = {tag: i for i, tag in enumerate(compatible_tags)}

    compatible: list[tuple[DistributionPackage, Version, int]] = []

    for pkg in packages:
        if pkg.package_type != "wheel":
            continue

        wheel_tags = parse_wheel_tags(pkg.filename)
        best_priority = float("inf")

        for tag in wheel_tags:
            if tag in tag_priority:
                best_priority = min(best_priority, tag_priority[tag])

        if best_priority < float("inf"):
            version = Version(pkg.version) if pkg.version else Version("0")
            compatible.append((pkg, version, int(best_priority)))

    if not compatible:
        return None

    # Sort by version (descending), then tag priority (ascending)
    compatible.sort(key=lambda x: (-x[1].major, -x[1].minor, -x[1].micro, x[2]))
    return compatible[0][0]


def list_wheels(
    package: str,
    index_url: str = "https://pypi.org/simple/",
) -> list[DistributionPackage]:
    """List available wheel files for a package."""
    with PyPISimple(index_url) as client:
        page = client.get_project_page(package)
        return [p for p in page.packages if p.package_type == "wheel"]


def download_compatible_wheel(
    package: str,
    output_dir: Path,
    index_url: str = "https://pypi.org/simple/",
    version: str | None = None,
    python_version: str | None = None,
    show_progress: bool = True,
) -> Path | None:
    """Download the best compatible wheel for the current platform.

    Args:
        package: Package name
        output_dir: Directory to save the file
        index_url: Base URL of the simple repository index
        version: Optional version constraint (e.g., "1.0.0", "<2", ">=1.0,<2")
        python_version: Optional Python version (e.g., "3.12"). If None, uses current interpreter.
        show_progress: Whether to show download progress

    Returns:
        Path to downloaded wheel, or None if no compatible wheel found
    """
    from pathlib import Path as PathLib

    output_dir = PathLib(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with PyPISimple(index_url) as client:
        page = client.get_project_page(package)
        packages = list(page.packages)

        if not packages:
            print(f"No packages found for {package}", file=sys.stderr)
            return None

        wheels = [p for p in packages if p.package_type == "wheel"]

        if version:
            # Use packaging.specifiers for PEP 440 version matching
            specifier = SpecifierSet(version, prereleases=True)
            wheels = [w for w in wheels if w.version and Version(w.version) in specifier]
            if not wheels:
                print(f"No wheels found for {package} matching {version}", file=sys.stderr)
                return None

        compatible_tags = get_compatible_tags(python_version)
        wheel = best_wheel(wheels, compatible_tags)

        if wheel is None:
            print(f"No compatible wheel found for {package} on this platform", file=sys.stderr)
            return None

        if show_progress:
            print(f"Found: {wheel.filename}")

        output_path = output_dir / wheel.filename
        # verify=False because some indexes (like Anaconda.org) don't provide digests
        client.download_package(wheel, output_path, verify=False)
        return output_path
