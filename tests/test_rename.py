"""Tests for wheel renaming functionality."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from third_wheel.rename import (
    _build_wheel_filename,
    _find_package_dir,
    compute_record_hash,
    inspect_wheel,
    normalize_name,
    parse_wheel_filename,
    rename_wheel,
    rename_wheel_from_bytes,
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

    def test_rename_not_a_whl_extension(self, tmp_path: Path) -> None:
        """Test error when file is not a .whl."""
        tarball = tmp_path / "testpkg-0.1.0.tar.gz"
        tarball.write_bytes(b"fake")
        with pytest.raises(ValueError, match="Not a wheel file"):
            rename_wheel(tarball, "newname")

    def test_rename_update_imports_false(self, tmp_path: Path) -> None:
        """Test that update_imports=False skips import rewriting."""
        wheel_path = tmp_path / "testpkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("testpkg/__init__.py", "from testpkg.core import main\n")
            zf.writestr("testpkg/core.py", "def main(): pass\n")
            zf.writestr(
                "testpkg-0.1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: testpkg\nVersion: 0.1.0\n",
            )
            zf.writestr("testpkg-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
            zf.writestr("testpkg-0.1.0.dist-info/RECORD", "")

        result = rename_wheel(
            wheel_path, "testpkg_v1", output_dir=tmp_path / "out", update_imports=False
        )

        with zipfile.ZipFile(result, "r") as zf:
            init = zf.read("testpkg_v1/__init__.py").decode()
            # Imports should NOT be rewritten
            assert "from testpkg.core import main" in init

    def test_patch_strings_rewrites_string_literals(self, tmp_path: Path) -> None:
        """patch_strings=True rewrites string-based module references."""
        wheel_path = tmp_path / "zarr-3.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("zarr/__init__.py", "from zarr.core import Array\n")
            zf.writestr(
                "zarr/core.py",
                'PIPELINE = "zarr.core.codec_pipeline.BatchedCodecPipeline"\ndef Array(): pass\n',
            )
            zf.writestr(
                "zarr/config.py",
                "config = {\n"
                '    "default_pipeline": "zarr.core.codec_pipeline.BatchedCodecPipeline",\n'
                '    "file_ext": ".zarr",\n'  # should NOT be rewritten
                "}\n",
            )
            zf.writestr(
                "zarr-3.0.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: zarr\nVersion: 3.0.0\n",
            )
            zf.writestr("zarr-3.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
            zf.writestr("zarr-3.0.0.dist-info/RECORD", "")

        result = rename_wheel(
            wheel_path, "zarr_old", output_dir=tmp_path / "out", patch_strings=True
        )

        with zipfile.ZipFile(result, "r") as zf:
            core = zf.read("zarr_old/core.py").decode()
            # String reference should be rewritten
            assert "zarr_old.core.codec_pipeline.BatchedCodecPipeline" in core
            assert '"zarr.core.codec_pipeline' not in core

            config = zf.read("zarr_old/config.py").decode()
            # String reference should be rewritten
            assert "zarr_old.core.codec_pipeline.BatchedCodecPipeline" in config
            # File extension .zarr should NOT be rewritten
            assert '".zarr"' in config

            init = zf.read("zarr_old/__init__.py").decode()
            # Import should also be rewritten
            assert "from zarr_old.core import Array" in init

    def test_patch_strings_false_leaves_strings(self, tmp_path: Path) -> None:
        """patch_strings=False (default) does NOT rewrite string references."""
        wheel_path = tmp_path / "zarr-3.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr(
                "zarr/__init__.py",
                'PIPELINE = "zarr.core.codec_pipeline"\n',
            )
            zf.writestr(
                "zarr-3.0.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: zarr\nVersion: 3.0.0\n",
            )
            zf.writestr("zarr-3.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
            zf.writestr("zarr-3.0.0.dist-info/RECORD", "")

        result = rename_wheel(
            wheel_path, "zarr_old", output_dir=tmp_path / "out", patch_strings=False
        )

        with zipfile.ZipFile(result, "r") as zf:
            init = zf.read("zarr_old/__init__.py").decode()
            # String reference should NOT be rewritten (patch_strings=False)
            assert '"zarr.core.codec_pipeline"' in init


class TestParseWheelFilenameEdgeCases:
    def test_too_few_parts(self) -> None:
        with pytest.raises(ValueError, match="Invalid wheel filename"):
            parse_wheel_filename("foo-1.0.whl")

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid wheel filename"):
            parse_wheel_filename(".whl")

    def test_build_tag_counted_from_end(self) -> None:
        """Build tag detection works by counting from the end, not guessing."""
        result = parse_wheel_filename("pkg-1.0.0-1build1-cp311-cp311-linux_x86_64.whl")
        assert result["distribution"] == "pkg"
        assert result["version"] == "1.0.0"
        assert result["build"] == "1build1"
        assert result["python"] == "cp311"
        assert result["abi"] == "cp311"
        assert result["platform"] == "linux_x86_64"


class TestRenameWheelFromBytes:
    def _make_wheel_bytes(self, name: str = "testpkg", version: str = "1.0.0") -> bytes:
        """Create minimal wheel bytes for testing."""
        from io import BytesIO

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{name}/__init__.py", f'VERSION = "{version}"\n')
            zf.writestr(
                f"{name}-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            )
            zf.writestr(
                f"{name}-{version}.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr(f"{name}-{version}.dist-info/RECORD", "")
        return buf.getvalue()

    def test_basic_rename(self) -> None:
        wheel_bytes = self._make_wheel_bytes()
        result = rename_wheel_from_bytes(wheel_bytes, "testpkg_v1")

        from io import BytesIO

        with zipfile.ZipFile(BytesIO(result), "r") as zf:
            names = zf.namelist()
            assert "testpkg_v1/__init__.py" in names
            assert "testpkg_v1-1.0.0.dist-info/METADATA" in names
            metadata = zf.read("testpkg_v1-1.0.0.dist-info/METADATA").decode()
            assert "Name: testpkg_v1" in metadata

    def test_same_name_returns_original(self) -> None:
        wheel_bytes = self._make_wheel_bytes()
        result = rename_wheel_from_bytes(wheel_bytes, "testpkg")
        assert result is wheel_bytes

    def test_no_dist_info_raises(self) -> None:
        from io import BytesIO

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("standalone.py", "print('hello')")
        with pytest.raises(ValueError, match=r"Cannot find \.dist-info"):
            rename_wheel_from_bytes(buf.getvalue(), "newname")

    def test_malformed_dist_info_raises(self) -> None:
        from io import BytesIO

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("nodash.dist-info/METADATA", "Name: nodash\n")
            zf.writestr("nodash.dist-info/RECORD", "")
        with pytest.raises(ValueError, match="Cannot parse version"):
            rename_wheel_from_bytes(buf.getvalue(), "newname")

    def test_update_imports_false(self) -> None:
        from io import BytesIO

        wheel_bytes = self._make_wheel_bytes()
        result = rename_wheel_from_bytes(wheel_bytes, "testpkg_v1", update_imports=False)

        with zipfile.ZipFile(BytesIO(result), "r") as zf:
            init = zf.read("testpkg_v1/__init__.py").decode()
            # Original content preserved (no import rewriting)
            assert 'VERSION = "1.0.0"' in init


class TestInspectWheel:
    def test_pure_python_wheel(self, tmp_path: Path) -> None:
        wheel_path = tmp_path / "testpkg-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("testpkg/__init__.py", "")
            zf.writestr("testpkg-1.0.0.dist-info/METADATA", "Name: testpkg\n")
            zf.writestr("testpkg-1.0.0.dist-info/WHEEL", "")
            zf.writestr("testpkg-1.0.0.dist-info/RECORD", "")

        info = inspect_wheel(wheel_path)
        assert info["distribution"] == "testpkg"
        assert info["version"] == "1.0.0"
        assert info["extensions"] == []
        assert info["has_underscore_prefix_extension"] is False

    def test_wheel_with_extension(self, tmp_path: Path) -> None:
        wheel_path = tmp_path / "testpkg-1.0.0-cp311-cp311-linux_x86_64.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("testpkg/__init__.py", "")
            zf.writestr("testpkg/_core.cpython-311-x86_64-linux-gnu.so", b"\x00")
            zf.writestr("testpkg-1.0.0.dist-info/METADATA", "Name: testpkg\n")
            zf.writestr("testpkg-1.0.0.dist-info/WHEEL", "")
            zf.writestr("testpkg-1.0.0.dist-info/RECORD", "")

        info = inspect_wheel(wheel_path)
        assert len(info["extensions"]) == 1  # type: ignore[arg-type]
        ext = info["extensions"][0]  # type: ignore[index]
        assert ext["module_name"] == "_core"
        assert ext["has_underscore_prefix"] is True
        assert info["has_underscore_prefix_extension"] is True

    def test_wheel_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            inspect_wheel(tmp_path / "nonexistent.whl")

    def test_json_serializable(self, tmp_path: Path) -> None:
        """inspect_wheel output should be JSON-serializable (used by --json flag)."""
        import json

        wheel_path = tmp_path / "testpkg-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("testpkg/__init__.py", "")
            zf.writestr("testpkg-1.0.0.dist-info/METADATA", "Name: testpkg\n")
            zf.writestr("testpkg-1.0.0.dist-info/WHEEL", "")
            zf.writestr("testpkg-1.0.0.dist-info/RECORD", "")

        info = inspect_wheel(wheel_path)
        # Should not raise
        json.dumps(info)


class TestCacheDir:
    def test_default_path(self) -> None:
        from unittest.mock import patch as mock_patch

        from third_wheel.run import cache_dir

        with mock_patch.dict("os.environ", {}, clear=True):
            result = cache_dir()
            assert result == Path.home() / ".cache" / "third-wheel"

    def test_env_override(self, tmp_path: Path) -> None:
        from unittest.mock import patch as mock_patch

        from third_wheel.run import cache_dir

        with mock_patch.dict(
            "os.environ", {"THIRD_WHEEL_CACHE_DIR": str(tmp_path / "custom")}, clear=True
        ):
            result = cache_dir()
            assert result == tmp_path / "custom"

    def test_xdg_cache_home(self, tmp_path: Path) -> None:
        from unittest.mock import patch as mock_patch

        from third_wheel.run import cache_dir

        with mock_patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path / "xdg")}, clear=True):
            result = cache_dir()
            assert result == tmp_path / "xdg" / "third-wheel"

    def test_env_override_takes_priority_over_xdg(self, tmp_path: Path) -> None:
        from unittest.mock import patch as mock_patch

        from third_wheel.run import cache_dir

        with mock_patch.dict(
            "os.environ",
            {
                "THIRD_WHEEL_CACHE_DIR": str(tmp_path / "custom"),
                "XDG_CACHE_HOME": str(tmp_path / "xdg"),
            },
            clear=True,
        ):
            result = cache_dir()
            assert result == tmp_path / "custom"


class TestRenameCacheKey:
    def test_stable_hash(self) -> None:
        from third_wheel.run import RenameSpec, rename_cache_key

        renames = [RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")]
        key1 = rename_cache_key(renames, "https://pypi.org/simple/", None)
        key2 = rename_cache_key(renames, "https://pypi.org/simple/", None)
        assert key1 == key2

    def test_differs_on_version(self) -> None:
        from third_wheel.run import RenameSpec, rename_cache_key

        r1 = [RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")]
        r2 = [RenameSpec(original="icechunk", new_name="icechunk_v1", version="<3")]
        assert rename_cache_key(r1, "https://pypi.org/simple/", None) != rename_cache_key(
            r2, "https://pypi.org/simple/", None
        )

    def test_differs_on_index_url(self) -> None:
        from third_wheel.run import RenameSpec, rename_cache_key

        renames = [RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")]
        key1 = rename_cache_key(renames, "https://pypi.org/simple/", None)
        key2 = rename_cache_key(renames, "https://other.org/simple/", None)
        assert key1 != key2

    def test_differs_on_python_version(self) -> None:
        from third_wheel.run import RenameSpec, rename_cache_key

        renames = [RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")]
        key1 = rename_cache_key(renames, "https://pypi.org/simple/", "3.11")
        key2 = rename_cache_key(renames, "https://pypi.org/simple/", "3.12")
        assert key1 != key2

    def test_order_independent(self) -> None:
        from third_wheel.run import RenameSpec, rename_cache_key

        r1 = [
            RenameSpec(original="a", new_name="a_v1"),
            RenameSpec(original="b", new_name="b_v1"),
        ]
        r2 = [
            RenameSpec(original="b", new_name="b_v1"),
            RenameSpec(original="a", new_name="a_v1"),
        ]
        assert rename_cache_key(r1, "https://pypi.org/simple/", None) == rename_cache_key(
            r2, "https://pypi.org/simple/", None
        )
