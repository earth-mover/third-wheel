"""Tests for third_wheel.download module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from packaging.tags import Tag
from pypi_simple import DistributionPackage

from tests.conftest import create_test_wheel, install_wheel_in_venv, run_in_venv
from third_wheel.cli import main
from third_wheel.download import best_wheel, parse_wheel_tags


# Test fixture helpers
def _package(version: str, tag: str = "py3-none-any") -> DistributionPackage:
    filename = f"samplepkg-{version}-{tag}.whl"
    return DistributionPackage(
        filename=filename,
        url=f"https://example.test/{filename}",
        project="samplepkg",
        version=version,
        package_type="wheel",
        digests={},
        requires_python=None,
        has_sig=None,
    )


# End test fixture helpers


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("2.0.dev1", "2.0.dev2"),
        ("2.0rc1", "2.0rc2"),
        ("2.0rc2", "2.0"),
        ("2.0", "2.0.post1"),
        ("2.0.0.1", "2.0.0.2"),
        ("3.0", "1!2.0"),
    ],
)
def test_best_wheel_orders_full_versions(older: str, newer: str) -> None:
    older_wheel = _package(older)
    newer_wheel = _package(newer)

    assert best_wheel([older_wheel, newer_wheel], [Tag("py3", "none", "any")]) == newer_wheel


def test_best_wheel_still_prefers_more_specific_compatible_tag() -> None:
    generic = _package("2.0")
    specific = _package("2.0", "cp313-cp313-macosx_14_0_arm64")
    unsupported = _package("3.0", "cp313-cp313-win_amd64")
    tags = [Tag("cp313", "cp313", "macosx_14_0_arm64"), Tag("py3", "none", "any")]

    assert best_wheel([generic, unsupported, specific], tags) == specific


def test_download_renames_and_installs_latest_matching_release_candidate(
    tmp_path: Path, dual_install_venv: Path
) -> None:
    source = tmp_path / "index"
    source.mkdir()
    versions = ("2.0rc1", "2.0rc2", "2.0")
    for version in versions:
        create_test_wheel(source, "samplepkg", version)

    def download_from_fixture(
        package: DistributionPackage, destination: Path, *, verify: bool
    ) -> None:
        assert not verify
        destination.write_bytes((source / package.filename).read_bytes())

    output = tmp_path / "wheels"
    with patch("third_wheel.download.PyPISimple") as index:
        client = index.return_value.__enter__.return_value
        client.get_project_page.return_value.packages = [_package(v) for v in versions]
        client.download_package.side_effect = download_from_fixture
        result = CliRunner().invoke(
            main,
            [
                "download",
                "samplepkg",
                "--version",
                ">=2.0rc1,<=2.0rc2",
                "--rename",
                "samplepkg_rc",
                "-o",
                str(output),
            ],
        )

    assert result.exit_code == 0, result.output
    wheel = output / "samplepkg_rc-2.0rc2-py3-none-any.whl"
    assert list(output.glob("*.whl")) == [wheel]
    install_wheel_in_venv(dual_install_venv, wheel)
    installed = run_in_venv(
        dual_install_venv, "import samplepkg_rc; print(samplepkg_rc.__version__)"
    )
    assert installed.returncode == 0, installed.stderr
    assert installed.stdout.strip() == "2.0rc2"


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
