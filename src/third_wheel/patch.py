"""Patch dependency references in a wheel without renaming the package.

While third-wheel's ``rename`` rewrites a package's own name and internal imports,
``patch`` rewrites references to a *dependency* throughout a wheel.

Use case: after renaming ``zarr`` to ``zarr_v2``, any package that ``import zarr``
(like ``anemoi-datasets``) needs its references updated too.

CLI::

    third-wheel patch anemoi_datasets-0.5.31-py3-none-any.whl zarr zarr_v2 -o ./wheels/

Python API::

    from third_wheel.patch import patch_wheel, patch_wheel_from_bytes

    result = patch_wheel(
        Path("anemoi_datasets-0.5.31-py3-none-any.whl"),
        old_dep="zarr",
        new_dep="zarr_v2",
        output_dir=Path("./wheels/"),
    )
"""

from __future__ import annotations

import re
import zipfile
from typing import TYPE_CHECKING

from third_wheel.rename import compute_record_hash

if TYPE_CHECKING:
    from pathlib import Path


def _update_dependency_references(content: bytes, old_name: str, new_name: str) -> bytes:
    """Rewrite all references to a dependency in Python source.

    Handles:
    - ``import old`` → ``import new``
    - ``from old import ...`` → ``from new import ...``
    - ``from old.sub import ...`` → ``from new.sub import ...``
    - ``old.attr`` → ``new.attr`` (dotted usage references)

    Does NOT rewrite:
    - File extensions like ``.zarr`` (preceded by a dot)
    - Partial matches (e.g., ``lazy_zarr``) — uses word boundaries

    Uses a negative lookbehind for ``.`` to avoid rewriting file extensions.
    """
    text = content.decode("utf-8")
    text = re.sub(rf"(?<!\.)\b{re.escape(old_name)}\b", new_name, text)
    return text.encode("utf-8")


def patch_wheel(
    wheel_path: Path,
    old_dep: str,
    new_dep: str,
    output_dir: Path | None = None,
) -> tuple[Path, list[str]]:
    """Rewrite dependency references in a wheel without renaming the package.

    This rewrites all Python source references from ``old_dep`` to ``new_dep``
    inside the wheel. The wheel's own package name, dist-info, and metadata
    remain unchanged.

    Args:
        wheel_path: Path to the input wheel file
        old_dep: Old dependency name to replace (e.g., ``"zarr"``)
        new_dep: New dependency name (e.g., ``"zarr_v2"``)
        output_dir: Output directory (default: same as input, overwrites)

    Returns:
        Tuple of (path to patched wheel, list of patched filenames)
    """
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")
    if wheel_path.suffix != ".whl":
        raise ValueError(f"Not a wheel file: {wheel_path}")
    if old_dep == new_dep:
        raise ValueError(f"Old and new dependency names are the same: {old_dep}")

    if output_dir is None:
        output_dir = wheel_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / wheel_path.name

    files: dict[str, bytes] = {}
    patched_files: list[str] = []
    record_filename: str | None = None

    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            content = zf.read(name)

            if name.endswith(".dist-info/RECORD"):
                record_filename = name
                continue

            if name.endswith(".py"):
                new_content = _update_dependency_references(content, old_dep, new_dep)
                if new_content != content:
                    patched_files.append(name)
                    content = new_content

            files[name] = content

    # Regenerate RECORD
    if record_filename:
        record_lines: list[str] = []
        for file_name, content in sorted(files.items()):
            file_hash = compute_record_hash(content)
            file_size = len(content)
            record_lines.append(f"{file_name},{file_hash},{file_size}")
        record_lines.append(f"{record_filename},,")
        files[record_filename] = "\n".join(record_lines).encode("utf-8")

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_name, content in sorted(files.items()):
            zf.writestr(file_name, content)

    return output_path, patched_files


def patch_wheel_from_bytes(
    wheel_bytes: bytes,
    old_dep: str,
    new_dep: str,
) -> tuple[bytes, list[str]]:
    """Rewrite dependency references in a wheel from bytes (for in-memory processing).

    Args:
        wheel_bytes: Original wheel file contents as bytes
        old_dep: Old dependency name to replace
        new_dep: New dependency name

    Returns:
        Tuple of (patched wheel bytes, list of patched filenames)
    """
    from io import BytesIO

    if old_dep == new_dep:
        return wheel_bytes, []

    input_buffer = BytesIO(wheel_bytes)
    files: dict[str, bytes] = {}
    patched_files: list[str] = []
    record_filename: str | None = None

    with zipfile.ZipFile(input_buffer, "r") as zf:
        for name in zf.namelist():
            content = zf.read(name)

            if name.endswith(".dist-info/RECORD"):
                record_filename = name
                continue

            if name.endswith(".py"):
                new_content = _update_dependency_references(content, old_dep, new_dep)
                if new_content != content:
                    patched_files.append(name)
                    content = new_content

            files[name] = content

    if record_filename:
        record_lines: list[str] = []
        for file_name, content in sorted(files.items()):
            file_hash = compute_record_hash(content)
            file_size = len(content)
            record_lines.append(f"{file_name},{file_hash},{file_size}")
        record_lines.append(f"{record_filename},,")
        files[record_filename] = "\n".join(record_lines).encode("utf-8")

    output_buffer = BytesIO()
    with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_name, content in sorted(files.items()):
            zf.writestr(file_name, content)

    return output_buffer.getvalue(), patched_files
