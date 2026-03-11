"""Wheel streaming and on-the-fly renaming."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from third_wheel.server.upstream import UpstreamClient


async def rename_wheel_bytes(
    wheel_bytes: bytes,
    new_name: str,
) -> bytes:
    """Rename a wheel from bytes.

    Args:
        wheel_bytes: Original wheel bytes
        new_name: New package name

    Returns:
        Renamed wheel bytes
    """
    from third_wheel.rename import rename_wheel_from_bytes

    return rename_wheel_from_bytes(wheel_bytes, new_name)


async def stream_and_patch_wheel(
    client: UpstreamClient,
    upstream_url: str,
    old_dep: str,
    new_dep: str,
) -> bytes:
    """Download wheel from upstream and patch dependency references.

    Args:
        client: Upstream client to download from
        upstream_url: URL of the original wheel
        old_dep: Dependency name to replace
        new_dep: Replacement dependency name

    Returns:
        Patched wheel bytes
    """
    from third_wheel.patch import patch_wheel_from_bytes

    wheel_bytes = await client.download_wheel(upstream_url)
    patched_bytes, _patched_files = patch_wheel_from_bytes(wheel_bytes, old_dep, new_dep)
    return patched_bytes


async def stream_and_rename_wheel(
    client: UpstreamClient,
    upstream_url: str,
    new_name: str,
) -> bytes:
    """Download wheel from upstream and rename it.

    This downloads the entire wheel into memory, renames it, and returns
    the renamed bytes. For very large wheels, this could use significant
    memory, but most wheels are <100MB which is acceptable.

    Args:
        client: Upstream client to download from
        upstream_url: URL of the original wheel
        new_name: New package name

    Returns:
        Renamed wheel bytes
    """
    # Download complete wheel
    wheel_bytes = await client.download_wheel(upstream_url)

    # Rename in memory
    return await rename_wheel_bytes(wheel_bytes, new_name)


def rewrite_wheel_filename(filename: str, original_name: str, new_name: str) -> str:
    """Rewrite a wheel filename with a new package name.

    Args:
        filename: Original wheel filename
        original_name: Original package name
        new_name: New package name

    Returns:
        Rewritten filename
    """
    from third_wheel.rename import _build_wheel_filename, normalize_name, parse_wheel_filename

    try:
        components = parse_wheel_filename(filename)
    except ValueError:
        # Fall back to simple replacement if filename can't be parsed
        return filename.replace(f"{original_name}-", f"{new_name}-", 1)

    if normalize_name(components["distribution"]) == normalize_name(original_name):
        components["distribution"] = normalize_name(new_name)
    return _build_wheel_filename(components)


def original_filename_from_renamed(renamed_filename: str, original_name: str, new_name: str) -> str:
    """Get the original filename from a renamed filename.

    Args:
        renamed_filename: Renamed wheel filename
        original_name: Original package name
        new_name: New package name

    Returns:
        Original filename
    """
    from third_wheel.rename import _build_wheel_filename, normalize_name, parse_wheel_filename

    try:
        components = parse_wheel_filename(renamed_filename)
    except ValueError:
        return renamed_filename.replace(f"{new_name}-", f"{original_name}-", 1)

    if normalize_name(components["distribution"]) == normalize_name(new_name):
        components["distribution"] = normalize_name(original_name)
    return _build_wheel_filename(components)
