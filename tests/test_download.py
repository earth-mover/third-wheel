"""Tests for third_wheel.download module."""

from __future__ import annotations

from packaging.tags import Tag

from third_wheel.download import parse_wheel_tags


class TestParseWheelTags:
    def test_simple_platform_wheel(self):
        tags = parse_wheel_tags("numpy-1.24.0-cp312-cp312-manylinux_2_17_x86_64.whl")
        assert Tag("cp312", "cp312", "manylinux_2_17_x86_64") in tags

    def test_pure_python_py3(self):
        tags = parse_wheel_tags("requests-2.31.0-py3-none-any.whl")
        assert Tag("py3", "none", "any") in tags

    def test_py2_py3_universal_wheel(self):
        """Regression: py2.py3 tag must be split into two separate tags."""
        tags = parse_wheel_tags("urllib3-1.26.20-py2.py3-none-any.whl")
        assert Tag("py2", "none", "any") in tags
        assert Tag("py3", "none", "any") in tags

    def test_multiple_platform_tags(self):
        tags = parse_wheel_tags(
            "numpy-1.24.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        )
        assert Tag("cp312", "cp312", "manylinux_2_17_x86_64") in tags
        assert Tag("cp312", "cp312", "manylinux2014_x86_64") in tags

    def test_multiple_abi_tags(self):
        tags = parse_wheel_tags("pkg-1.0-cp312-cp312.abi3-linux_x86_64.whl")
        assert Tag("cp312", "cp312", "linux_x86_64") in tags
        assert Tag("cp312", "abi3", "linux_x86_64") in tags

    def test_build_tag_present(self):
        tags = parse_wheel_tags("pkg-1.0-1-py3-none-any.whl")
        assert Tag("py3", "none", "any") in tags

    def test_too_few_parts(self):
        tags = parse_wheel_tags("invalid-filename.whl")
        assert tags == []
