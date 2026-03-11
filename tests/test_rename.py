"""Tests for wheel renaming functionality."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from third_wheel.rename import (
    _build_wheel_filename,
    _find_package_dir,
    compute_record_hash,
    normalize_name,
    parse_wheel_filename,
    rename_wheel,
)


class TestNormalizeName:
    def test_lowercase(self) -> None:
        assert normalize_name("MyPackage") == "mypackage"

    def test_hyphens_to_underscores(self) -> None:
        assert normalize_name("my-package") == "my_package"

    def test_dots_to_underscores(self) -> None:
        assert normalize_name("my.package") == "my_package"

    def test_multiple_separators(self) -> None:
        assert normalize_name("My--Package..Name") == "my_package_name"


class TestParseWheelFilename:
    def test_basic_wheel(self) -> None:
        result = parse_wheel_filename("mypackage-1.0.0-py3-none-any.whl")
        assert result["distribution"] == "mypackage"
        assert result["version"] == "1.0.0"
        assert result["python"] == "py3"
        assert result["abi"] == "none"
        assert result["platform"] == "any"

    def test_wheel_with_build_tag(self) -> None:
        result = parse_wheel_filename("mypackage-1.0.0-1-py3-none-any.whl")
        assert result["distribution"] == "mypackage"
        assert result["version"] == "1.0.0"
        assert result["build"] == "1"
        assert result["python"] == "py3"

    def test_platform_wheel(self) -> None:
        result = parse_wheel_filename(
            "numpy-1.24.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        )
        assert result["distribution"] == "numpy"
        assert result["version"] == "1.24.0"
        assert result["python"] == "cp311"
        assert result["abi"] == "cp311"


class TestBuildWheelFilename:
    def test_basic(self) -> None:
        components = {
            "distribution": "mypackage",
            "version": "1.0.0",
            "build": "",
            "python": "py3",
            "abi": "none",
            "platform": "any",
        }
        assert _build_wheel_filename(components) == "mypackage-1.0.0-py3-none-any.whl"

    def test_with_build_tag(self) -> None:
        components = {
            "distribution": "mypackage",
            "version": "1.0.0",
            "build": "1",
            "python": "py3",
            "abi": "none",
            "platform": "any",
        }
        assert _build_wheel_filename(components) == "mypackage-1.0.0-1-py3-none-any.whl"


class TestComputeRecordHash:
    def test_known_hash(self) -> None:
        # Test with known input
        data = b"hello world"
        result = compute_record_hash(data)
        assert result.startswith("sha256=")
        # SHA256 of "hello world" is known
        assert result == "sha256=uU0nuZNNPgilLlLX2n2r-sSE7-N6U4DukIj3rOLvzek"


class TestFindPackageDir:
    def test_matching_names(self) -> None:
        """When dist name matches the package dir, returns None."""
        namelist = [
            "mypackage/__init__.py",
            "mypackage/core.py",
            "mypackage-1.0.0.dist-info/METADATA",
            "mypackage-1.0.0.dist-info/RECORD",
        ]
        assert _find_package_dir(namelist, "mypackage", "1.0.0") is None

    def test_mismatched_names(self) -> None:
        """Detects when import name differs from dist name (e.g. scikit_image -> skimage)."""
        namelist = [
            "skimage/__init__.py",
            "skimage/filters/__init__.py",
            "skimage/feature/__init__.py",
            "scikit_image-0.24.0.dist-info/METADATA",
            "scikit_image-0.24.0.dist-info/RECORD",
        ]
        assert _find_package_dir(namelist, "scikit_image", "0.24.0") == "skimage"

    def test_pillow_case(self) -> None:
        """Detects Pillow -> PIL mismatch."""
        namelist = [
            "PIL/__init__.py",
            "PIL/Image.py",
            "pillow-10.0.0.dist-info/METADATA",
            "pillow-10.0.0.dist-info/RECORD",
        ]
        assert _find_package_dir(namelist, "pillow", "10.0.0") == "PIL"

    def test_multiple_packages_picks_largest(self) -> None:
        """When multiple package dirs exist, picks the one with most files."""
        namelist = [
            "mainpkg/__init__.py",
            "mainpkg/a.py",
            "mainpkg/b.py",
            "mainpkg/c.py",
            "helper/__init__.py",
            "mypkg-1.0.0.dist-info/METADATA",
            "mypkg-1.0.0.dist-info/RECORD",
        ]
        assert _find_package_dir(namelist, "mypkg", "1.0.0") == "mainpkg"

    def test_no_packages_returns_none(self) -> None:
        """When there are no package dirs with __init__.py, returns None."""
        namelist = [
            "mypkg-1.0.0.dist-info/METADATA",
            "mypkg-1.0.0.dist-info/RECORD",
            "standalone.py",
        ]
        assert _find_package_dir(namelist, "mypkg", "1.0.0") is None


class TestRenameWheel:
    def test_rename_pure_python_wheel(self, tmp_path: Path) -> None:
        """Test renaming a simple pure Python wheel."""
        # Create a minimal wheel
        wheel_name = "testpkg-0.1.0-py3-none-any.whl"
        wheel_path = tmp_path / wheel_name

        # Create wheel contents
        with zipfile.ZipFile(wheel_path, "w") as zf:
            # Package directory
            zf.writestr("testpkg/__init__.py", 'VERSION = "0.1.0"\n')

            # Dist-info
            zf.writestr(
                "testpkg-0.1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: testpkg\nVersion: 0.1.0\n",
            )
            zf.writestr(
                "testpkg-0.1.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("testpkg-0.1.0.dist-info/RECORD", "")

        # Rename the wheel
        output_dir = tmp_path / "output"
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=output_dir)

        # Check the result
        assert result.exists()
        assert result.name == "testpkg_v1-0.1.0-py3-none-any.whl"

        # Verify contents
        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
            assert "testpkg_v1/__init__.py" in names
            assert "testpkg_v1-0.1.0.dist-info/METADATA" in names
            assert "testpkg_v1-0.1.0.dist-info/RECORD" in names

            # Check METADATA was updated
            metadata = zf.read("testpkg_v1-0.1.0.dist-info/METADATA").decode()
            assert "Name: testpkg_v1" in metadata

    def test_rename_mismatched_import_name(self, tmp_path: Path) -> None:
        """Test renaming a wheel where import name differs from distribution name.

        Simulates scikit-image (dist name: scikit_image, import name: skimage).
        """
        wheel_name = "scikit_image-0.24.0-py3-none-any.whl"
        wheel_path = tmp_path / wheel_name

        with zipfile.ZipFile(wheel_path, "w") as zf:
            # Package uses "skimage" as the import name, not "scikit_image"
            zf.writestr("skimage/__init__.py", '__version__ = "0.24.0"\n')
            zf.writestr("skimage/filters/__init__.py", "from skimage.filters.edges import sobel\n")
            zf.writestr("skimage/filters/edges.py", "def sobel(img): pass\n")
            zf.writestr(
                "skimage/feature/__init__.py", "from skimage.feature.corner import harris\n"
            )
            zf.writestr("skimage/feature/corner.py", "def harris(img): pass\n")

            zf.writestr(
                "scikit_image-0.24.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: scikit-image\nVersion: 0.24.0\n",
            )
            zf.writestr(
                "scikit_image-0.24.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("scikit_image-0.24.0.dist-info/RECORD", "")

        output_dir = tmp_path / "output"
        result = rename_wheel(wheel_path, "skimage_old", output_dir=output_dir)

        assert result.exists()
        assert result.name == "skimage_old-0.24.0-py3-none-any.whl"

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()

            # Package dir should be renamed from skimage/ to skimage_old/
            assert "skimage_old/__init__.py" in names
            assert "skimage_old/filters/__init__.py" in names
            assert "skimage_old/filters/edges.py" in names
            assert "skimage_old/feature/__init__.py" in names
            assert "skimage_old/feature/corner.py" in names

            # No leftover skimage/ entries
            assert not any(n.startswith("skimage/") for n in names)

            # Dist-info should use the new name
            assert "skimage_old-0.24.0.dist-info/METADATA" in names
            assert "skimage_old-0.24.0.dist-info/RECORD" in names

            # METADATA should have new name
            metadata = zf.read("skimage_old-0.24.0.dist-info/METADATA").decode()
            assert "Name: skimage_old" in metadata

            # Imports inside Python files should be rewritten
            filters_init = zf.read("skimage_old/filters/__init__.py").decode()
            assert "from skimage_old.filters.edges import sobel" in filters_init

            feature_init = zf.read("skimage_old/feature/__init__.py").decode()
            assert "from skimage_old.feature.corner import harris" in feature_init

    def test_rename_wheel_not_found(self, tmp_path: Path) -> None:
        """Test error when wheel doesn't exist."""
        with pytest.raises(FileNotFoundError):
            rename_wheel(tmp_path / "nonexistent.whl", "newname")

    def test_rename_same_name_error(self, tmp_path: Path) -> None:
        """Test error when new name is the same as old name."""
        wheel_path = tmp_path / "testpkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("testpkg/__init__.py", "")
            zf.writestr("testpkg-0.1.0.dist-info/METADATA", "Name: testpkg\n")
            zf.writestr("testpkg-0.1.0.dist-info/WHEEL", "")
            zf.writestr("testpkg-0.1.0.dist-info/RECORD", "")

        with pytest.raises(ValueError, match="same as old name"):
            rename_wheel(wheel_path, "testpkg")
