"""Core wheel renaming logic."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def normalize_name(name: str) -> str:
    """Normalize a package name according to PEP 503."""
    return re.sub(r"[-_.]+", "_", name).lower()


def compute_record_hash(data: bytes) -> str:
    """Compute SHA256 hash in RECORD format (base64 urlsafe, no padding)."""
    import base64

    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def parse_wheel_filename(filename: str) -> dict[str, str]:
    """Parse a wheel filename into its components.

    Format: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    """
    name = Path(filename).stem  # Remove .whl
    parts = name.split("-")

    if len(parts) < 5:
        raise ValueError(f"Invalid wheel filename: {filename}")

    # Check if there's a build tag (starts with a digit)
    if len(parts) >= 6 and parts[2][0].isdigit():
        return {
            "distribution": parts[0],
            "version": parts[1],
            "build": parts[2],
            "python": parts[3],
            "abi": parts[4],
            "platform": parts[5],
        }
    else:
        return {
            "distribution": parts[0],
            "version": parts[1],
            "build": "",
            "python": parts[2],
            "abi": parts[3],
            "platform": parts[4],
        }


def _build_wheel_filename(components: dict[str, str]) -> str:
    """Build a wheel filename from components."""
    parts = [components["distribution"], components["version"]]
    if components.get("build"):
        parts.append(components["build"])
    parts.extend([components["python"], components["abi"], components["platform"]])
    return "-".join(parts) + ".whl"


def _iter_wheel_files(wheel_path: Path) -> Iterator[tuple[str, bytes]]:
    """Iterate over all files in a wheel, yielding (name, content) tuples."""
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            yield name, zf.read(name)


def _update_metadata(content: bytes, _old_name: str, new_name: str) -> bytes:
    """Update the METADATA file with the new package name."""
    text = content.decode("utf-8")
    lines = text.split("\n")
    new_lines = []

    for line in lines:
        if line.startswith("Name:"):
            # Replace the package name
            new_lines.append(f"Name: {new_name}")
        else:
            new_lines.append(line)

    return "\n".join(new_lines).encode("utf-8")


def _update_python_imports(content: bytes, old_name: str, new_name: str) -> bytes:
    """Update Python file imports that reference the old package name.

    This handles common patterns like:
    - from old_name import ...
    - import old_name
    - from old_name.submodule import ...
    """
    text = content.decode("utf-8")

    # Pattern to match imports (be careful not to replace partial matches)
    # Only replace if old_name is a complete module name (word boundary)
    patterns = [
        (rf"\bfrom {re.escape(old_name)}(\s|\.)", rf"from {new_name}\1"),
        (rf"\bimport {re.escape(old_name)}\b", f"import {new_name}"),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)

    return text.encode("utf-8")


def _find_package_dir(namelist: list[str], dist_name: str, version: str) -> str | None:
    """Find the actual top-level package directory inside a wheel.

    Some packages have a different import name than their distribution name
    (e.g., scikit-image -> skimage, Pillow -> PIL, opencv-python -> cv2).
    This function discovers the real package directory by excluding known
    non-package directories (dist-info, data).

    Returns the package directory name if it differs from dist_name, or None
    if they match.
    """
    dist_info = f"{dist_name}-{version}.dist-info"
    data_dir = f"{dist_name}-{version}.data"

    # If the distribution name is already a top-level dir, no mismatch
    if any(n.startswith(f"{dist_name}/") for n in namelist):
        return None

    # Find top-level directories that have __init__.py (Python packages)
    init_files = {name for name in namelist if name.endswith("/__init__.py")}
    pkg_dirs = set()
    for name in init_files:
        top = name.split("/")[0]
        if top != dist_info and top != data_dir:
            pkg_dirs.add(top)

    if len(pkg_dirs) == 1:
        return pkg_dirs.pop()

    # Multiple packages — pick the one with the most files
    if pkg_dirs:
        dir_counts = {}
        for d in pkg_dirs:
            dir_counts[d] = sum(1 for n in namelist if n.startswith(f"{d}/"))
        return max(dir_counts, key=dir_counts.get)  # type: ignore[arg-type]

    return None


def rename_wheel(
    wheel_path: Path,
    new_name: str,
    output_dir: Path | None = None,
    *,
    update_imports: bool = True,
) -> Path:
    """Rename a wheel package.

    Args:
        wheel_path: Path to the input wheel file
        new_name: New package name (e.g., "icechunk_v1")
        output_dir: Output directory for the renamed wheel (default: same as input)
        update_imports: Whether to update import statements in Python files

    Returns:
        Path to the renamed wheel file
    """
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    if not wheel_path.suffix == ".whl":
        raise ValueError(f"Not a wheel file: {wheel_path}")

    # Parse the original wheel filename
    components = parse_wheel_filename(wheel_path.name)
    old_name = components["distribution"]
    old_name_normalized = normalize_name(old_name)
    new_name_normalized = normalize_name(new_name)

    if old_name_normalized == new_name_normalized:
        raise ValueError(f"New name '{new_name}' is the same as old name '{old_name}'")

    # Determine output path
    if output_dir is None:
        output_dir = wheel_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    components["distribution"] = new_name_normalized
    new_wheel_name = _build_wheel_filename(components)
    output_path = output_dir / new_wheel_name

    # Discover the actual package directory (may differ from distribution name)
    with zipfile.ZipFile(wheel_path, "r") as zf:
        pkg_dir = _find_package_dir(zf.namelist(), old_name_normalized, components["version"])
    old_import_name = pkg_dir if pkg_dir else old_name_normalized

    # Process the wheel
    files: dict[str, bytes] = {}

    # Old and new dist-info directory names
    old_dist_info = f"{old_name_normalized}-{components['version']}.dist-info"
    new_dist_info = f"{new_name_normalized}-{components['version']}.dist-info"

    # Old and new data directory names (if present)
    old_data_dir = f"{old_name_normalized}-{components['version']}.data"
    new_data_dir = f"{new_name_normalized}-{components['version']}.data"

    for name, content in _iter_wheel_files(wheel_path):
        new_file_name = name

        # Rename the package directory
        if name.startswith(f"{old_import_name}/") or name == old_import_name:
            new_file_name = new_name_normalized + name[len(old_import_name) :]

        # Rename the dist-info directory
        elif name.startswith(f"{old_dist_info}/") or name == old_dist_info:
            new_file_name = new_dist_info + name[len(old_dist_info) :]

        # Rename the data directory (if present)
        elif name.startswith(f"{old_data_dir}/") or name == old_data_dir:
            new_file_name = new_data_dir + name[len(old_data_dir) :]

        # Update file contents as needed
        new_content = content

        # Update METADATA file
        if new_file_name == f"{new_dist_info}/METADATA":
            new_content = _update_metadata(content, old_name, new_name)

        # Update Python files (imports)
        elif update_imports and new_file_name.endswith(".py"):
            new_content = _update_python_imports(content, old_import_name, new_name_normalized)

        # Skip the old RECORD file (we'll generate a new one)
        if name.endswith("/RECORD"):
            continue

        files[new_file_name] = new_content

    # Generate new RECORD file
    record_path = f"{new_dist_info}/RECORD"
    record_lines: list[str] = []

    for file_name, content in sorted(files.items()):
        file_hash = compute_record_hash(content)
        file_size = len(content)
        record_lines.append(f"{file_name},{file_hash},{file_size}")

    # RECORD itself has no hash
    record_lines.append(f"{record_path},,")
    record_content = "\n".join(record_lines).encode("utf-8")
    files[record_path] = record_content

    # Write the new wheel
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_name, content in sorted(files.items()):
            zf.writestr(file_name, content)

    return output_path


def rename_wheel_from_bytes(
    wheel_bytes: bytes,
    new_name: str,
    *,
    update_imports: bool = True,
) -> bytes:
    """Rename a wheel from bytes (for in-memory processing).

    Args:
        wheel_bytes: Original wheel file contents as bytes
        new_name: New package name (e.g., "icechunk_v1")
        update_imports: Whether to update import statements in Python files

    Returns:
        Renamed wheel file contents as bytes
    """
    from io import BytesIO

    # Read the wheel from bytes
    input_buffer = BytesIO(wheel_bytes)

    with zipfile.ZipFile(input_buffer, "r") as zf:
        # Find the distribution name from the wheel
        dist_info_dirs = [n for n in zf.namelist() if ".dist-info/" in n]
        if not dist_info_dirs:
            msg = "Cannot find .dist-info directory in wheel"
            raise ValueError(msg)

        # Extract version from dist-info directory name
        dist_info_name = dist_info_dirs[0].split("/")[0]  # e.g., "icechunk-1.0.0.dist-info"
        parts = dist_info_name.replace(".dist-info", "").rsplit("-", 1)
        old_name_normalized = parts[0]
        version = parts[1] if len(parts) > 1 else "0.0.0"

        new_name_normalized = normalize_name(new_name)

        if old_name_normalized == new_name_normalized:
            return wheel_bytes  # No rename needed

        # Discover the actual package directory (may differ from distribution name)
        pkg_dir = _find_package_dir(zf.namelist(), old_name_normalized, version)
        old_import_name = pkg_dir if pkg_dir else old_name_normalized

        # Old and new dist-info directory names
        old_dist_info = f"{old_name_normalized}-{version}.dist-info"
        new_dist_info = f"{new_name_normalized}-{version}.dist-info"

        # Old and new data directory names (if present)
        old_data_dir = f"{old_name_normalized}-{version}.data"
        new_data_dir = f"{new_name_normalized}-{version}.data"

        # Process files
        files: dict[str, bytes] = {}

        for name in zf.namelist():
            content = zf.read(name)
            new_file_name = name

            # Rename the package directory
            if name.startswith(f"{old_import_name}/") or name == old_import_name:
                new_file_name = new_name_normalized + name[len(old_import_name) :]

            # Rename the dist-info directory
            elif name.startswith(f"{old_dist_info}/") or name == old_dist_info:
                new_file_name = new_dist_info + name[len(old_dist_info) :]

            # Rename the data directory (if present)
            elif name.startswith(f"{old_data_dir}/") or name == old_data_dir:
                new_file_name = new_data_dir + name[len(old_data_dir) :]

            # Update file contents as needed
            new_content = content

            # Update METADATA file
            if new_file_name == f"{new_dist_info}/METADATA":
                new_content = _update_metadata(content, old_name_normalized, new_name)

            # Update Python files (imports)
            elif update_imports and new_file_name.endswith(".py"):
                new_content = _update_python_imports(content, old_import_name, new_name_normalized)

            # Skip the old RECORD file (we'll generate a new one)
            if name.endswith("/RECORD"):
                continue

            files[new_file_name] = new_content

    # Generate new RECORD file
    record_path = f"{new_dist_info}/RECORD"
    record_lines: list[str] = []

    for file_name, content in sorted(files.items()):
        file_hash = compute_record_hash(content)
        file_size = len(content)
        record_lines.append(f"{file_name},{file_hash},{file_size}")

    # RECORD itself has no hash
    record_lines.append(f"{record_path},,")
    record_content = "\n".join(record_lines).encode("utf-8")
    files[record_path] = record_content

    # Write the new wheel to bytes
    output_buffer = BytesIO()
    with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_name, content in sorted(files.items()):
            zf.writestr(file_name, content)

    return output_buffer.getvalue()


def inspect_wheel(wheel_path: Path) -> dict[str, object]:
    """Inspect a wheel and return information about its structure.

    This is useful for understanding the wheel structure before renaming,
    especially for compiled extensions.
    """
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    components = parse_wheel_filename(wheel_path.name)

    info: dict[str, object] = {
        "filename": wheel_path.name,
        "distribution": components["distribution"],
        "version": components["version"],
        "python_tag": components["python"],
        "abi_tag": components["abi"],
        "platform_tag": components["platform"],
        "files": [],
        "extensions": [],
        "has_underscore_prefix_extension": False,
    }

    files_list: list[str] = []
    extensions_list: list[dict[str, str]] = []

    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            files_list.append(name)

            # Check for compiled extensions
            if any(name.endswith(ext) for ext in (".so", ".pyd", ".dylib")):
                ext_name = Path(name).stem.split(".")[
                    0
                ]  # e.g., _icechunk from _icechunk.cpython-311-darwin
                has_underscore = ext_name.startswith("_")
                extensions_list.append(
                    {
                        "path": name,
                        "module_name": ext_name,
                        "has_underscore_prefix": str(has_underscore),
                    }
                )
                if has_underscore:
                    info["has_underscore_prefix_extension"] = True

    info["files"] = files_list
    info["extensions"] = extensions_list

    return info
