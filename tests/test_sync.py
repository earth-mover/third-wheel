"""Tests for third_wheel.sync module.

Covers pyproject.toml parsing, wheel lookup, pyproject.toml modification,
the sync/add CLI commands, caching, force re-download, installer selection,
and pixi/conda environment detection.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tests.conftest import (
    create_test_wheel,
    get_venv_pip,
    install_wheel_in_venv,
    run_in_venv,
)
from third_wheel.cli import main
from third_wheel.rename import rename_wheel
from third_wheel.run import RenameSpec
from third_wheel.sync import (
    _find_wheel_in_directory,
    add_rename_to_pyproject,
    add_rename_to_script,
    get_pyproject_config,
    parse_renames_from_pyproject,
)

# ---------------------------------------------------------------------------
# Unit tests: parse_renames_from_pyproject
# ---------------------------------------------------------------------------


class TestParseRenamesFromPyproject:
    """Test parsing rename specs from pyproject.toml files.

    Note: comment-style annotations (``"pkg_v1",  # pkg<2``) are NOT supported
    in pyproject.toml due to false-positive risk (ruff config, commented deps,
    etc.). Only ``[tool.third-wheel].renames`` structured metadata is read.
    """

    def test_comment_annotations_are_ignored(self, tmp_path: Path) -> None:
        """Comment annotations in [project].dependencies are NOT detected."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
            dependencies = [
                "icechunk_v1",  # icechunk<2
                "icechunk>=2",
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert renames == []

    def test_comment_annotations_in_dependency_groups_are_ignored(self, tmp_path: Path) -> None:
        """Comment annotations in [dependency-groups] are NOT detected."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [dependency-groups]
            test = [
                "icechunk_v1",  # icechunk<2
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert renames == []

    def test_structured_renames_in_tool_table(self, tmp_path: Path) -> None:
        """Structured [tool.third-wheel] renames are parsed correctly."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version == "<2"

    def test_structured_only_no_comments(self, tmp_path: Path) -> None:
        """Only structured renames are found; comments alongside are ignored."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
            dependencies = [
                "icechunk_v1",  # icechunk<3
            ]

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert len(renames) == 1
        # Only the structured form is read
        assert renames[0].version == "<2"

    def test_multiple_structured_renames(self, tmp_path: Path) -> None:
        """Multiple structured renames are all parsed."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
                {original = "zarr", new-name = "zarr_v2", version = "<3"},
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert len(renames) == 2
        names = {r.new_name for r in renames}
        assert names == {"icechunk_v1", "zarr_v2"}

    def test_ignores_ruff_config_comments(self, tmp_path: Path) -> None:
        """Ruff lint config comments like "F",  # Pyflakes are NOT treated as renames."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
            dependencies = []

            [tool.ruff.lint]
            select = [
                "F",    # Pyflakes
                "I",    # isort
                "UP",   # pyupgrade
                "B",    # flake8-bugbear
                "C4",   # flake8-comprehensions
                "PIE",  # flake8-pie
                "PGH",  # pygrep-hooks
                "PERF", # Perflint
            ]

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = ">=1,<2"},
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        # Should only find the real rename, not the ruff comments
        assert len(renames) == 1
        assert renames[0].new_name == "icechunk_v1"

    def test_empty_dependencies(self, tmp_path: Path) -> None:
        """Pyproject with empty dependency lists returns no renames."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
            dependencies = []
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert renames == []

    def test_no_renames_in_file(self, tmp_path: Path) -> None:
        """A pyproject with normal dependencies returns empty list."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
            dependencies = [
                "requests>=2",
                "numpy",
            ]
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert renames == []

    def test_minimal_pyproject(self, tmp_path: Path) -> None:
        """A minimal pyproject with just [project] returns empty list."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        renames = parse_renames_from_pyproject(pyproject)
        assert renames == []


# ---------------------------------------------------------------------------
# Unit tests: get_pyproject_config
# ---------------------------------------------------------------------------


class TestGetPyprojectConfig:
    """Test reading optional config from [tool.third-wheel]."""

    def test_reads_index_url(self, tmp_path: Path) -> None:
        """Reads index-url from [tool.third-wheel]."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            index-url = "https://pypi.anaconda.org/nightly/simple"
        """)
        )

        config = get_pyproject_config(pyproject)
        assert config["index_url"] == "https://pypi.anaconda.org/nightly/simple"

    def test_missing_tool_section(self, tmp_path: Path) -> None:
        """Returns empty dict when [tool.third-wheel] is absent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        config = get_pyproject_config(pyproject)
        assert config == {}

    def test_missing_index_url_key(self, tmp_path: Path) -> None:
        """Returns empty dict when section exists but index-url is absent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = []
        """)
        )

        config = get_pyproject_config(pyproject)
        assert config == {}

    def test_invalid_toml(self, tmp_path: Path) -> None:
        """Returns empty dict for invalid TOML content."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is not valid toml {{{")

        config = get_pyproject_config(pyproject)
        assert config == {}


# ---------------------------------------------------------------------------
# Unit tests: add_rename_to_pyproject
# ---------------------------------------------------------------------------


class TestAddRenameToPyproject:
    """Test modifying pyproject.toml to add rename entries."""

    def test_creates_tool_section_when_missing(self, tmp_path: Path) -> None:
        """Creates [tool.third-wheel] section when it doesn't exist."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec("icechunk", "icechunk_v1", "<2")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert "[tool.third-wheel]" in content
        assert 'original = "icechunk"' in content
        assert 'new-name = "icechunk_v1"' in content
        assert 'version = "<2"' in content

    def test_appends_to_existing_renames(self, tmp_path: Path) -> None:
        """Appends new entry to an existing renames list."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        spec = RenameSpec("zarr", "zarr_v2", "<3")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'original = "zarr"' in content
        assert 'new-name = "zarr_v2"' in content
        # Original entry should still be there
        assert 'original = "icechunk"' in content

    def test_updates_existing_entry_with_same_new_name(self, tmp_path: Path) -> None:
        """Updates an existing entry when the same new-name is used."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        spec = RenameSpec("icechunk", "icechunk_v1", "<1.5")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'version = "<1.5"' in content
        # Old version should be gone
        assert 'version = "<2"' not in content

    def test_handles_version_specifier(self, tmp_path: Path) -> None:
        """Version specifier is included in the TOML entry."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec("zarr", "zarr_v2", ">=2.0,<3")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'version = ">=2.0,<3"' in content

    def test_handles_no_version_specifier(self, tmp_path: Path) -> None:
        """Entry without version omits the version field."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec("requests", "my_requests")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'original = "requests"' in content
        assert 'new-name = "my_requests"' in content
        # No version key should appear
        assert "version" not in content

    def test_creates_renames_key_when_section_exists_without_it(self, tmp_path: Path) -> None:
        """Adds renames key when [tool.third-wheel] exists but has no renames."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            index-url = "https://example.com/simple"
        """)
        )

        spec = RenameSpec("icechunk", "icechunk_v1", "<2")
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert "renames = [" in content
        assert 'original = "icechunk"' in content
        # index-url should still be there
        assert "index-url" in content

    def test_with_source_field(self, tmp_path: Path) -> None:
        """Source field is included in the TOML entry."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec(
            "zarr", "zarr_dev", source="git+https://github.com/zarr-developers/zarr-python@main"
        )
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'original = "zarr"' in content
        assert 'new-name = "zarr_dev"' in content
        assert 'source = "git+https://github.com/zarr-developers/zarr-python@main"' in content
        # No version key when not specified
        assert "version" not in content

    def test_with_source_and_version(self, tmp_path: Path) -> None:
        """Both source and version are included in the TOML entry."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec(
            "zarr",
            "zarr_dev",
            version=">=3",
            source="git+https://github.com/zarr-developers/zarr-python@main",
        )
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert 'version = ">=3"' in content
        assert 'source = "git+https://github.com/zarr-developers/zarr-python@main"' in content

    def test_source_roundtrip(self, tmp_path: Path) -> None:
        """Source field survives write then parse roundtrip."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec(
            "zarr", "zarr_dev", source="git+https://github.com/zarr-developers/zarr-python@main"
        )
        add_rename_to_pyproject(pyproject, spec)

        renames = parse_renames_from_pyproject(pyproject)
        assert len(renames) == 1
        assert renames[0].source == "git+https://github.com/zarr-developers/zarr-python@main"
        assert renames[0].source_type == "git"

    def test_update_source_on_existing_entry(self, tmp_path: Path) -> None:
        """Updating an existing entry replaces the source field."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "zarr", new-name = "zarr_dev", source = "git+https://github.com/zarr-developers/zarr-python@v3.0"},
            ]
        """)
        )

        spec = RenameSpec(
            "zarr", "zarr_dev", source="git+https://github.com/zarr-developers/zarr-python@main"
        )
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert "@main" in content
        assert "@v3.0" not in content


# ---------------------------------------------------------------------------
# Unit tests: add_rename_to_pyproject idempotency
# ---------------------------------------------------------------------------


class TestAddRenameToPyprojectIdempotency:
    """Verify that add_rename_to_pyproject is safe to call repeatedly.

    These tests guard against accidental duplication, corruption, or data loss
    when the same rename is added multiple times, versions are changed, or
    several packages are interleaved.
    """

    def _count_entries(self, content: str, new_name: str) -> int:
        """Count how many times a new-name appears as a TOML inline-table entry."""
        import re

        return len(re.findall(rf'new-name\s*=\s*"{re.escape(new_name)}"', content))

    def test_same_spec_twice_no_duplication(self, tmp_path: Path) -> None:
        """Adding the exact same rename twice produces exactly one entry."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        spec = RenameSpec("icechunk", "icechunk_v1", "<2")
        add_rename_to_pyproject(pyproject, spec)
        add_rename_to_pyproject(pyproject, spec)

        content = pyproject.read_text()
        assert self._count_entries(content, "icechunk_v1") == 1

    def test_version_update_no_duplication(self, tmp_path: Path) -> None:
        """Updating the version of an existing rename doesn't create a second entry."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<2"))
        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<1.5"))

        content = pyproject.read_text()
        assert self._count_entries(content, "icechunk_v1") == 1
        assert 'version = "<1.5"' in content
        assert 'version = "<2"' not in content

    def test_multiple_packages_stay_separate(self, tmp_path: Path) -> None:
        """Adding different packages produces one entry each, no cross-contamination."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<2"))
        add_rename_to_pyproject(pyproject, RenameSpec("zarr", "zarr_v2", "<3"))
        add_rename_to_pyproject(pyproject, RenameSpec("xarray", "xarray_v1", "<2024"))

        content = pyproject.read_text()
        assert self._count_entries(content, "icechunk_v1") == 1
        assert self._count_entries(content, "zarr_v2") == 1
        assert self._count_entries(content, "xarray_v1") == 1

    def test_interleaved_adds_and_updates(self, tmp_path: Path) -> None:
        """Interleaving adds and updates for multiple packages stays consistent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        # Add icechunk
        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<2"))
        # Add zarr
        add_rename_to_pyproject(pyproject, RenameSpec("zarr", "zarr_v2", "<3"))
        # Update icechunk version
        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<1.5"))
        # Add zarr again (same)
        add_rename_to_pyproject(pyproject, RenameSpec("zarr", "zarr_v2", "<3"))
        # Update zarr version
        add_rename_to_pyproject(pyproject, RenameSpec("zarr", "zarr_v2", ">=2,<3"))

        content = pyproject.read_text()
        assert self._count_entries(content, "icechunk_v1") == 1
        assert self._count_entries(content, "zarr_v2") == 1
        assert 'version = "<1.5"' in content
        assert 'version = ">=2,<3"' in content

    def test_result_is_valid_toml(self, tmp_path: Path) -> None:
        """After multiple add/update operations, the file is still valid TOML."""
        import tomllib

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<2"))
        add_rename_to_pyproject(pyproject, RenameSpec("zarr", "zarr_v2", "<3"))
        add_rename_to_pyproject(pyproject, RenameSpec("icechunk", "icechunk_v1", "<1.5"))
        add_rename_to_pyproject(pyproject, RenameSpec("numpy", "numpy_v1"))

        content = pyproject.read_text()
        data = tomllib.loads(content)
        renames = data["tool"]["third-wheel"]["renames"]
        assert len(renames) == 3
        names = {r["new-name"] for r in renames}
        assert names == {"icechunk_v1", "zarr_v2", "numpy_v1"}

    def test_add_without_version_then_with_version(self, tmp_path: Path) -> None:
        """Adding without version, then with version, updates correctly."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        add_rename_to_pyproject(pyproject, RenameSpec("requests", "my_requests"))
        content_before = pyproject.read_text()
        assert "version" not in content_before

        add_rename_to_pyproject(pyproject, RenameSpec("requests", "my_requests", "<3"))
        content_after = pyproject.read_text()
        assert 'version = "<3"' in content_after
        assert self._count_entries(content_after, "my_requests") == 1


class TestAddCLIIdempotency:
    """Verify the ``third-wheel add`` CLI command is idempotent."""

    def test_cli_add_same_spec_twice(self, tmp_path: Path) -> None:
        """Running ``add`` twice with identical args produces one entry."""
        runner = CliRunner()
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "myproject"\n')

        for _ in range(2):
            result = runner.invoke(
                main,
                ["add", "icechunk<2=icechunk_v1", "--pyproject", str(pyproject)],
            )
            assert result.exit_code == 0, result.output

        import tomllib

        data = tomllib.loads(pyproject.read_text())
        renames = data["tool"]["third-wheel"]["renames"]
        assert len(renames) == 1
        assert renames[0]["new-name"] == "icechunk_v1"

    def test_cli_add_update_version(self, tmp_path: Path) -> None:
        """Running ``add`` with a new version replaces the old entry."""
        runner = CliRunner()
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "myproject"\n')

        runner.invoke(
            main,
            ["add", "icechunk<2=icechunk_v1", "--pyproject", str(pyproject)],
        )
        runner.invoke(
            main,
            ["add", "icechunk<1.5=icechunk_v1", "--pyproject", str(pyproject)],
        )

        import tomllib

        data = tomllib.loads(pyproject.read_text())
        renames = data["tool"]["third-wheel"]["renames"]
        assert len(renames) == 1
        assert renames[0]["version"] == "<1.5"

    def test_cli_add_multiple_packages_then_duplicates(self, tmp_path: Path) -> None:
        """Adding 3 packages then re-adding each one still gives exactly 3."""
        runner = CliRunner()
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "myproject"\n')

        specs = [
            "icechunk<2=icechunk_v1",
            "zarr<3=zarr_v2",
            "xarray<2024=xarray_v1",
        ]

        # Add all three
        for spec in specs:
            runner.invoke(main, ["add", spec, "--pyproject", str(pyproject)])

        # Re-add all three
        for spec in specs:
            runner.invoke(main, ["add", spec, "--pyproject", str(pyproject)])

        import tomllib

        data = tomllib.loads(pyproject.read_text())
        renames = data["tool"]["third-wheel"]["renames"]
        assert len(renames) == 3
        names = {r["new-name"] for r in renames}
        assert names == {"icechunk_v1", "zarr_v2", "xarray_v1"}


# ---------------------------------------------------------------------------
# Unit tests: _find_wheel_in_directory
# ---------------------------------------------------------------------------


class TestFindWheelInDirectory:
    """Test local wheel lookup by name and version."""

    def test_finds_matching_wheel(self, tmp_path: Path) -> None:
        """Finds a wheel matching the package name."""
        create_test_wheel(tmp_path, "mypkg", "1.0.0")

        result = _find_wheel_in_directory(tmp_path, "mypkg", None)
        assert result is not None
        assert result.name == "mypkg-1.0.0-py3-none-any.whl"

    def test_applies_version_constraint(self, tmp_path: Path) -> None:
        """Respects a version specifier when searching."""
        create_test_wheel(tmp_path, "mypkg", "1.0.0")
        create_test_wheel(tmp_path, "mypkg", "2.0.0")

        result = _find_wheel_in_directory(tmp_path, "mypkg", "<2")
        assert result is not None
        assert "1.0.0" in result.name

    def test_returns_highest_version(self, tmp_path: Path) -> None:
        """Returns the highest matching version when multiple wheels match."""
        create_test_wheel(tmp_path, "mypkg", "1.0.0")
        create_test_wheel(tmp_path, "mypkg", "1.5.0")
        create_test_wheel(tmp_path, "mypkg", "2.0.0")

        result = _find_wheel_in_directory(tmp_path, "mypkg", "<2")
        assert result is not None
        assert "1.5.0" in result.name

    def test_returns_none_when_no_match(self, tmp_path: Path) -> None:
        """Returns None when no wheel matches the constraints."""
        create_test_wheel(tmp_path, "mypkg", "2.0.0")

        result = _find_wheel_in_directory(tmp_path, "mypkg", "<1")
        assert result is None

    def test_returns_none_for_wrong_package(self, tmp_path: Path) -> None:
        """Returns None when the requested package name is not present."""
        create_test_wheel(tmp_path, "otherpkg", "1.0.0")

        result = _find_wheel_in_directory(tmp_path, "mypkg", None)
        assert result is None

    def test_ignores_non_wheel_files(self, tmp_path: Path) -> None:
        """Non-.whl files in the directory are ignored."""
        create_test_wheel(tmp_path, "mypkg", "1.0.0")
        (tmp_path / "mypkg-1.0.0.tar.gz").write_text("not a wheel")
        (tmp_path / "README.md").write_text("readme")

        result = _find_wheel_in_directory(tmp_path, "mypkg", None)
        assert result is not None
        assert result.suffix == ".whl"

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Returns None for an empty directory."""
        result = _find_wheel_in_directory(tmp_path, "mypkg", None)
        assert result is None


# ---------------------------------------------------------------------------
# Helpers for mocking uv pip install
# ---------------------------------------------------------------------------


def _make_mock_uv_pip_install(venv_dir: Path):
    """Return a mock for subprocess.run that redirects uv pip install to a venv."""
    original_run = __import__("subprocess").run

    def mock_run(cmd: list[str], **kwargs: Any) -> Any:
        if cmd[:3] == ["uv", "pip", "install"]:
            pip = get_venv_pip(venv_dir)
            new_cmd = [str(pip), "install", *cmd[3:]]
            return original_run(new_cmd, **kwargs)
        return original_run(cmd, **kwargs)

    return mock_run


def _make_mock_noop_install():
    """Return a mock that records uv pip install calls without doing anything."""
    install_calls: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: Any) -> Any:
        if cmd[:3] == ["uv", "pip", "install"]:
            install_calls.append(cmd)
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return __import__("subprocess").run(cmd, **kwargs)

    return mock_run, install_calls


# ---------------------------------------------------------------------------
# Integration tests: sync with find_links (local wheels, no network)
# ---------------------------------------------------------------------------


class TestSyncWithFindLinks:
    """Test sync() using local wheels via --find-links."""

    def test_sync_installs_renamed_wheel(self, tmp_path: Path, dual_install_venv: Path) -> None:
        """sync() with find_links renames and installs the wheel."""
        from third_wheel.sync import sync

        # Create a wheel in a "source" directory
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        with patch(
            "third_wheel.sync.subprocess.run",
            side_effect=_make_mock_uv_pip_install(dual_install_venv),
        ):
            installed = sync(renames, find_links=source_dir)

        assert len(installed) == 1
        assert "mypkg_v1" in installed[0].name

        # Verify it's importable in the venv
        result = run_in_venv(
            dual_install_venv,
            "import mypkg_v1; print(mypkg_v1.get_version())",
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "1.0.0" in result.stdout


class TestSyncSelfReferential:
    """Test the icechunk pattern: a project installs an older version of itself."""

    def test_self_referential_dual_install(self, tmp_path: Path, dual_install_venv: Path) -> None:
        """Simulate the icechunk pattern: import mypkg (v2) and mypkg_v1 (v1)."""
        # Create v1 wheel in a "wheels" directory
        wheels_dir = tmp_path / "wheels"
        wheels_dir.mkdir()
        create_test_wheel(wheels_dir, "mypkg", "1.0.0")

        # Create v2 wheel and install it directly
        v2_wheel = create_test_wheel(tmp_path, "mypkg", "2.0.0")
        install_wheel_in_venv(dual_install_venv, v2_wheel)

        # Rename v1 and install it
        v1_source = _find_wheel_in_directory(wheels_dir, "mypkg", "<2")
        assert v1_source is not None

        renamed_dir = tmp_path / "renamed"
        renamed_dir.mkdir()
        shutil.copy2(v1_source, renamed_dir / v1_source.name)
        v1_renamed = rename_wheel(
            renamed_dir / v1_source.name,
            "mypkg_v1",
            output_dir=renamed_dir,
        )
        install_wheel_in_venv(dual_install_venv, v1_renamed)

        # Verify both versions are importable
        code = textwrap.dedent("""\
            import mypkg
            import mypkg_v1

            assert mypkg.get_version() == "2.0.0", f"Got {mypkg.get_version()}"
            assert mypkg_v1.get_version() == "1.0.0", f"Got {mypkg_v1.get_version()}"
            print("PASS")
        """)
        result = run_in_venv(dual_install_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout


class TestSyncCaching:
    """Test that repeated syncs use cached wheels."""

    def test_cached_wheels_are_reused(self, tmp_path: Path) -> None:
        """After a successful sync, a second sync uses the cache (no re-prepare)."""
        from third_wheel.sync import sync

        test_cache = tmp_path / "cache"
        test_cache.mkdir()

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        mock_run, install_calls = _make_mock_noop_install()

        with (
            patch("third_wheel.sync.subprocess.run", side_effect=mock_run),
            patch("third_wheel.sync.cache_dir", return_value=test_cache),
        ):
            # First sync: prepares wheels from source
            installed1 = sync(renames, find_links=source_dir)
            assert len(installed1) == 1

            # Second sync with same args: should use cache
            installed2 = sync(renames, find_links=source_dir)
            assert len(installed2) == 1

        # Both syncs should have called install
        assert len(install_calls) == 2

    def test_force_flag_re_prepares_wheels(self, tmp_path: Path) -> None:
        """sync(force=True) re-downloads even when wheels are cached."""
        import time

        from third_wheel.sync import sync

        test_cache_dir = tmp_path / "cache"
        test_cache_dir.mkdir()

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        mock_run, install_calls = _make_mock_noop_install()

        with (
            patch("third_wheel.sync.subprocess.run", side_effect=mock_run),
            patch("third_wheel.sync.cache_dir", return_value=test_cache_dir),
        ):
            # First sync
            sync(renames, find_links=source_dir)

            # Find the cached wheel
            cached_wheels = list((test_cache_dir / "sync").rglob("*.whl"))
            assert len(cached_wheels) == 1
            mtime_before = cached_wheels[0].stat().st_mtime

            # Small delay so mtime changes
            time.sleep(0.05)

            # Force re-sync: should re-prepare the wheel
            sync(renames, find_links=source_dir, force=True)

            cached_wheels_after = list((test_cache_dir / "sync").rglob("*.whl"))
            assert len(cached_wheels_after) == 1
            # The wheel was recreated
            mtime_after = cached_wheels_after[0].stat().st_mtime
            assert mtime_after > mtime_before

        assert len(install_calls) == 2


# ---------------------------------------------------------------------------
# Unit tests: installer selection
# ---------------------------------------------------------------------------


class TestInstallerSelection:
    """Test explicit --installer uv/pip selection."""

    def test_installer_uv_uses_uv_pip(self, tmp_path: Path) -> None:
        """installer='uv' runs 'uv pip install'."""
        from third_wheel.sync import sync

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        mock_run, install_calls = _make_mock_noop_install()

        with patch("third_wheel.sync.subprocess.run", side_effect=mock_run):
            sync(renames, find_links=source_dir, installer="uv")

        assert len(install_calls) == 1
        assert install_calls[0][:3] == ["uv", "pip", "install"]

    def test_installer_pip_uses_pip_module(self, tmp_path: Path) -> None:
        """installer='pip' runs 'python -m pip install'."""
        import sys

        from third_wheel.sync import sync

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        install_calls: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> Any:
            # Check for pip install (python -m pip install)
            if len(cmd) >= 3 and cmd[1:3] == ["-m", "pip"]:
                install_calls.append(cmd)
                return SimpleNamespace(returncode=0, stderr="", stdout="")
            return subprocess.run(cmd, **kwargs)

        with patch("third_wheel.sync.subprocess.run", side_effect=mock_run):
            sync(renames, find_links=source_dir, installer="pip")

        assert len(install_calls) == 1
        assert install_calls[0][:3] == [sys.executable, "-m", "pip"]

    def test_batch_install_multiple_wheels(self, tmp_path: Path) -> None:
        """Multiple renames result in a single install command."""
        from third_wheel.sync import sync

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")
        create_test_wheel(source_dir, "mypkg", "2.0.0")

        renames = [
            RenameSpec("mypkg", "mypkg_v1", "<2"),
            RenameSpec("mypkg", "mypkg_v2", ">=2,<3"),
        ]

        mock_run, install_calls = _make_mock_noop_install()

        with patch("third_wheel.sync.subprocess.run", side_effect=mock_run):
            installed = sync(renames, find_links=source_dir)

        # Should be a single install command for both wheels
        assert len(install_calls) == 1
        # Both wheels should be in the command
        assert len(installed) == 2

    def test_install_failure_raises(self, tmp_path: Path) -> None:
        """sync() raises RuntimeError when installation fails."""
        from third_wheel.sync import sync

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        def failing_run(cmd: list[str], **kwargs: Any) -> Any:
            if cmd[:3] == ["uv", "pip", "install"]:
                return SimpleNamespace(returncode=1, stderr="some error", stdout="")
            return __import__("subprocess").run(cmd, **kwargs)

        with (
            patch("third_wheel.sync.subprocess.run", side_effect=failing_run),
            pytest.raises(RuntimeError, match="Failed to install"),
        ):
            sync(renames, find_links=source_dir)


# ---------------------------------------------------------------------------
# Unit tests: detect_installer
# ---------------------------------------------------------------------------


class TestDetectInstaller:
    """Test _detect_installer auto-detection logic."""

    def test_without_conda_prefix_uses_uv(self) -> None:
        """Without CONDA_PREFIX, returns plain uv pip install."""
        from third_wheel.sync import _detect_installer

        with patch.dict("os.environ", {}, clear=True):
            # Ensure CONDA_PREFIX is not set
            import os

            os.environ.pop("CONDA_PREFIX", None)
            cmd = _detect_installer()

        assert cmd == ["uv", "pip", "install"]

    def test_with_conda_prefix_uses_uv_with_python(self, tmp_path: Path) -> None:
        """With CONDA_PREFIX, returns uv pip install --python targeting the env."""
        from third_wheel.sync import _detect_installer

        # Create a fake conda env with a python binary
        fake_conda = tmp_path / "fake_conda"
        bin_dir = fake_conda / "bin"
        bin_dir.mkdir(parents=True)
        fake_python = bin_dir / "python"
        fake_python.write_text("#!/bin/sh\n")
        fake_python.chmod(0o755)

        with patch.dict("os.environ", {"CONDA_PREFIX": str(fake_conda)}):
            cmd = _detect_installer()

        assert cmd[:3] == ["uv", "pip", "install"]
        assert "--python" in cmd
        assert str(fake_python) in cmd


# ---------------------------------------------------------------------------
# Unit tests: index-url from pyproject.toml config
# ---------------------------------------------------------------------------


class TestSyncIndexUrlConfig:
    """Test that index-url from [tool.third-wheel] is used by sync CLI."""

    def test_pyproject_index_url_used_when_no_cli_flag(self, tmp_path: Path) -> None:
        """sync CLI uses index-url from pyproject.toml when -i is not given."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            index-url = "https://example.com/simple"
            renames = [
                {original = "mypkg", new-name = "mypkg_v1", version = "<2"},
            ]
        """)
        )

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                ["sync", "--pyproject", str(pyproject)],
            )

        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        assert call_kwargs.kwargs["index_url"] == "https://example.com/simple"

    def test_cli_index_url_overrides_pyproject(self, tmp_path: Path) -> None:
        """CLI -i flag overrides pyproject.toml index-url."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            index-url = "https://example.com/simple"
            renames = [
                {original = "mypkg", new-name = "mypkg_v1", version = "<2"},
            ]
        """)
        )

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                [
                    "sync",
                    "--pyproject",
                    str(pyproject),
                    "-i",
                    "https://override.com/simple",
                ],
            )

        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        assert call_kwargs.kwargs["index_url"] == "https://override.com/simple"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestSyncCLI:
    """Test the 'third-wheel sync' click command."""

    def test_sync_with_rename_flag(self, tmp_path: Path) -> None:
        """sync --rename flag is parsed and passed through."""
        runner = CliRunner()

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        # Create a minimal pyproject so the real project's pyproject isn't picked up
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "testproj"\n')

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                [
                    "sync",
                    "--rename",
                    "mypkg<2=mypkg_v1",
                    "--find-links",
                    str(source_dir),
                    "--pyproject",
                    str(pyproject),
                ],
            )

        # The command should have parsed the rename and called sync
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        renames = call_kwargs[0][0]  # first positional arg
        assert len(renames) == 1
        assert renames[0].original == "mypkg"
        assert renames[0].new_name == "mypkg_v1"
        assert renames[0].version == "<2"

    def test_sync_with_pyproject_auto_detection(self, tmp_path: Path) -> None:
        """sync reads renames from pyproject.toml when no --rename is given."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "mypkg", new-name = "mypkg_v1", version = "<2"},
            ]
        """)
        )

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        create_test_wheel(source_dir, "mypkg", "1.0.0")

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                [
                    "sync",
                    "--pyproject",
                    str(pyproject),
                    "--find-links",
                    str(source_dir),
                ],
            )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        renames = call_kwargs[0][0]
        assert len(renames) == 1
        assert renames[0].new_name == "mypkg_v1"

    def test_sync_no_renames_shows_message(self) -> None:
        """sync with no renames found prints a helpful message."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        assert "No renames found" in result.output

    def test_sync_verbose_flag(self) -> None:
        """The -v/--verbose flag is accepted without error."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(main, ["sync", "-v"])

        assert result.exit_code == 0

    def test_sync_force_flag(self, tmp_path: Path) -> None:
        """The --force flag is passed through to sync()."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "mypkg", new-name = "mypkg_v1", version = "<2"},
            ]
        """)
        )

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                ["sync", "--pyproject", str(pyproject), "--force"],
            )

        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        mock_sync.assert_called_once()
        assert mock_sync.call_args.kwargs["force"] is True


class TestAddCLI:
    """Test the 'third-wheel add' click command."""

    def test_add_creates_rename_entry(self, tmp_path: Path) -> None:
        """add writes a rename entry to pyproject.toml."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "icechunk<2=icechunk_v1",
                "--pyproject",
                str(pyproject),
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Added" in result.output

        # Verify pyproject.toml was modified
        content = pyproject.read_text()
        assert "[tool.third-wheel]" in content
        assert 'original = "icechunk"' in content
        assert 'new-name = "icechunk_v1"' in content
        assert 'version = "<2"' in content

    def test_add_without_version(self, tmp_path: Path) -> None:
        """add without a version specifier creates entry without version."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "requests=my_requests",
                "--pyproject",
                str(pyproject),
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        content = pyproject.read_text()
        assert 'original = "requests"' in content
        assert 'new-name = "my_requests"' in content
        # Should NOT contain a version key
        assert "version" not in content

    def test_add_to_existing_renames(self, tmp_path: Path) -> None:
        """add appends to an existing renames list."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "zarr<3=zarr_v2",
                "--pyproject",
                str(pyproject),
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        content = pyproject.read_text()
        assert 'original = "zarr"' in content
        assert 'original = "icechunk"' in content

    def test_add_fails_without_pyproject(self, tmp_path: Path) -> None:
        """add fails gracefully when pyproject.toml doesn't exist."""
        runner = CliRunner()

        result = runner.invoke(
            main,
            [
                "add",
                "icechunk<2=icechunk_v1",
                "--pyproject",
                str(tmp_path / "nonexistent.toml"),
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output or "Error" in result.output

    def test_add_updates_existing_entry(self, tmp_path: Path) -> None:
        """add updates the version when the same new-name already exists."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"

            [tool.third-wheel]
            renames = [
                {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            ]
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "icechunk<1.5=icechunk_v1",
                "--pyproject",
                str(pyproject),
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        content = pyproject.read_text()
        assert 'version = "<1.5"' in content
        assert 'version = "<2"' not in content

    def test_add_with_sync(self, tmp_path: Path) -> None:
        """add --sync adds the entry and runs sync."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        with patch("third_wheel.sync.sync") as mock_sync:
            mock_sync.return_value = []

            result = runner.invoke(
                main,
                [
                    "add",
                    "icechunk<2=icechunk_v1",
                    "--pyproject",
                    str(pyproject),
                    "--sync",
                ],
            )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Added" in result.output

        # Verify the entry was added to pyproject.toml
        content = pyproject.read_text()
        assert 'original = "icechunk"' in content

        # Verify sync was called
        mock_sync.assert_called_once()
        call_args = mock_sync.call_args
        renames = call_args[0][0]
        assert len(renames) == 1
        assert renames[0].new_name == "icechunk_v1"

    def test_add_with_source(self, tmp_path: Path) -> None:
        """add --source writes the source field to pyproject.toml."""
        runner = CliRunner()

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "myproject"
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "zarr=zarr_dev",
                "--source",
                "git+https://github.com/zarr-developers/zarr-python@main",
                "--pyproject",
                str(pyproject),
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Added" in result.output

        content = pyproject.read_text()
        assert 'original = "zarr"' in content
        assert 'new-name = "zarr_dev"' in content
        assert 'source = "git+https://github.com/zarr-developers/zarr-python@main"' in content

    def test_add_with_source_to_script(self, tmp_path: Path) -> None:
        """add --source --script writes the source field to a PEP 723 script."""
        runner = CliRunner()

        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            import numpy
        """)
        )

        result = runner.invoke(
            main,
            [
                "add",
                "--script",
                str(script),
                "zarr=zarr_dev",
                "--source",
                "git+https://github.com/zarr-developers/zarr-python@main",
            ],
        )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        content = script.read_text()
        assert 'source = "git+https://github.com/zarr-developers/zarr-python@main"' in content


# ---------------------------------------------------------------------------
# Unit tests: add_rename_to_script
# ---------------------------------------------------------------------------


class TestAddRenameToScript:
    """Test adding renames to PEP 723 inline scripts."""

    def test_adds_to_empty_script(self, tmp_path: Path) -> None:
        """Adds dependency and [tool.third-wheel] to a script with existing metadata."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # requires-python = ">=3.12"
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            import numpy
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")
        add_rename_to_script(script, spec)

        content = script.read_text()
        # Dependency added
        assert '"icechunk_v1"' in content
        # Structured rename added
        assert "[tool.third-wheel]" in content
        assert 'original = "icechunk"' in content
        assert 'new-name = "icechunk_v1"' in content
        assert 'version = "<2"' in content
        # Original content preserved
        assert "import numpy" in content

    def test_adds_to_script_with_existing_tool_section(self, tmp_path: Path) -> None:
        """Appends to existing [tool.third-wheel] renames."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "zarr_v2",
            # ]
            # [tool.third-wheel]
            # renames = [
            #   {original = "zarr", new-name = "zarr_v2", version = "<3"},
            # ]
            # ///
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")
        add_rename_to_script(script, spec)

        content = script.read_text()
        assert '"icechunk_v1"' in content
        assert 'new-name = "icechunk_v1"' in content
        # Original rename preserved
        assert 'new-name = "zarr_v2"' in content

    def test_updates_existing_rename(self, tmp_path: Path) -> None:
        """Updates an existing rename with the same new-name."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "icechunk_v1",
            # ]
            # [tool.third-wheel]
            # renames = [
            #   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
            # ]
            # ///
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1", version="<3")
        add_rename_to_script(script, spec)

        content = script.read_text()
        assert 'version = "<3"' in content
        assert 'version = "<2"' not in content

    def test_does_not_duplicate_dependency(self, tmp_path: Path) -> None:
        """Doesn't add the dependency if it's already there."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "icechunk_v1",
            # ]
            # ///
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")
        add_rename_to_script(script, spec)

        content = script.read_text()
        # The dep appears once in dependencies + once in renames entry = 2 total
        # But in the dependencies list itself, it should only appear once
        dep_occurrences = sum(
            1 for line in content.splitlines() if line.strip() == '#   "icechunk_v1",'
        )
        assert dep_occurrences == 1

    def test_no_metadata_block_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when no PEP 723 block exists."""
        script = tmp_path / "test.py"
        script.write_text("print('hello')\n")

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1")
        with pytest.raises(ValueError, match="No PEP 723"):
            add_rename_to_script(script, spec)

    def test_without_version(self, tmp_path: Path) -> None:
        """Adds rename without version constraint."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1")
        add_rename_to_script(script, spec)

        content = script.read_text()
        assert 'original = "icechunk"' in content
        assert "version" not in content.split("icechunk_v1")[1].split("}")[0]

    def test_result_is_valid_pep723(self, tmp_path: Path) -> None:
        """Result can be parsed back by parse_pep723_metadata."""
        from third_wheel.run import parse_all_renames, parse_pep723_metadata

        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # requires-python = ">=3.12"
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            import numpy
        """)
        )

        spec = RenameSpec(original="icechunk", new_name="icechunk_v1", version="<2")
        add_rename_to_script(script, spec)

        content = script.read_text()
        toml_str = parse_pep723_metadata(content)
        assert toml_str is not None

        renames = parse_all_renames(content)
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version == "<2"

    def test_source_field_in_script(self, tmp_path: Path) -> None:
        """Source field is included in the script metadata entry."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            import numpy
        """)
        )

        spec = RenameSpec(
            original="zarr",
            new_name="zarr_dev",
            source="git+https://github.com/zarr-developers/zarr-python@main",
        )
        add_rename_to_script(script, spec)

        content = script.read_text()
        assert 'source = "git+https://github.com/zarr-developers/zarr-python@main"' in content
        assert '"zarr_dev"' in content

    def test_source_roundtrip_in_script(self, tmp_path: Path) -> None:
        """Source field survives write then parse roundtrip in a script."""
        from third_wheel.run import parse_all_renames

        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            import numpy
        """)
        )

        spec = RenameSpec(
            original="zarr",
            new_name="zarr_dev",
            source="git+https://github.com/zarr-developers/zarr-python@main",
        )
        add_rename_to_script(script, spec)

        content = script.read_text()
        renames = parse_all_renames(content)
        assert len(renames) == 1
        assert renames[0].source == "git+https://github.com/zarr-developers/zarr-python@main"
        assert renames[0].source_type == "git"


class TestAddCLIScript:
    """Test `third-wheel add --script` CLI command."""

    def test_add_to_script(self, tmp_path: Path) -> None:
        """CLI adds rename to a script file."""
        script = tmp_path / "test.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///
        """)
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["add", "--script", str(script), "icechunk<2=icechunk_v1"],
        )
        assert result.exit_code == 0
        assert "Added" in result.output
        assert "test.py" in result.output

        content = script.read_text()
        assert '"icechunk_v1"' in content
        assert "[tool.third-wheel]" in content

    def test_add_to_nonexistent_script_errors(self) -> None:
        """CLI errors when script doesn't exist."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["add", "--script", "/nonexistent/script.py", "icechunk<2=icechunk_v1"],
        )
        assert result.exit_code != 0


class TestAddScriptIntegration:
    """Integration tests for add --script: full round-trip workflows."""

    def test_add_then_parse_round_trip(self, tmp_path: Path) -> None:
        """Add multiple renames via CLI, then verify they parse back correctly."""
        from third_wheel.run import parse_all_renames

        script = tmp_path / "multi.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # requires-python = ">=3.12"
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            print("hello")
        """)
        )

        runner = CliRunner()

        # Add first rename
        result = runner.invoke(
            main,
            ["add", "--script", str(script), "icechunk<2=icechunk_v1"],
        )
        assert result.exit_code == 0

        # Add second rename
        result = runner.invoke(
            main,
            ["add", "--script", str(script), "zarr<3=zarr_v2"],
        )
        assert result.exit_code == 0

        # Parse the result — both renames should be found
        content = script.read_text()
        renames = parse_all_renames(content)
        assert len(renames) == 2

        names = {r.new_name for r in renames}
        assert names == {"icechunk_v1", "zarr_v2"}

        originals = {r.original for r in renames}
        assert originals == {"icechunk", "zarr"}

        # Dependencies should include both new names and numpy
        assert '"icechunk_v1"' in content
        assert '"zarr_v2"' in content
        assert '"numpy"' in content

    def test_add_update_round_trip(self, tmp_path: Path) -> None:
        """Add a rename, then update its version, verify only latest remains."""
        from third_wheel.run import parse_all_renames

        script = tmp_path / "update.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = []
            # ///
        """)
        )

        runner = CliRunner()

        # Add with version <2
        runner.invoke(
            main,
            ["add", "--script", str(script), "icechunk<2=icechunk_v1"],
        )

        # Update to version <3
        runner.invoke(
            main,
            ["add", "--script", str(script), "icechunk<3=icechunk_v1"],
        )

        renames = parse_all_renames(script.read_text())
        assert len(renames) == 1
        assert renames[0].version == "<3"

    def test_add_to_script_with_comment_annotations_preserves_them(self, tmp_path: Path) -> None:
        """Adding structured rename to script with comment annotations keeps both."""
        from third_wheel.run import parse_all_renames

        script = tmp_path / "mixed.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "pandas_v2",  # pandas<2
            #   "pandas>=2",
            # ]
            # ///
        """)
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["add", "--script", str(script), "zarr<3=zarr_v2"],
        )
        assert result.exit_code == 0

        content = script.read_text()
        renames = parse_all_renames(content)

        # Both the comment-style and structured renames should be found
        names = {r.new_name for r in renames}
        assert "pandas_v2" in names
        assert "zarr_v2" in names

    def test_add_to_script_then_find_links_sync(self, tmp_path: Path) -> None:
        """Full workflow: add rename to script, create wheel, verify metadata is valid."""
        # Create a test wheel
        v1_dir = tmp_path / "wheels"
        v1_dir.mkdir()
        v1_wheel = create_test_wheel(v1_dir, "mypkg", "1.0.0")

        # Rename it
        renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=v1_dir)
        assert renamed.exists()

        # Create a script and add rename via CLI
        script = tmp_path / "script.py"
        script.write_text(
            textwrap.dedent("""\
            # /// script
            # dependencies = [
            #   "numpy",
            # ]
            # ///

            print("test")
        """)
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["add", "--script", str(script), "mypkg<2=mypkg_v1"],
        )
        assert result.exit_code == 0

        # Verify the script has valid metadata that run module can parse
        from third_wheel.run import parse_all_renames, parse_pep723_metadata

        content = script.read_text()
        toml_str = parse_pep723_metadata(content)
        assert toml_str is not None

        renames = parse_all_renames(content)
        assert len(renames) == 1
        assert renames[0].original == "mypkg"
        assert renames[0].new_name == "mypkg_v1"
        assert renames[0].version == "<2"


# ---------------------------------------------------------------------------
# Integration tests: additive rename workflow
# ---------------------------------------------------------------------------


class TestSyncAdditive:
    """Test that sync() adds renamed packages without breaking existing installs."""

    def test_sync_is_additive_to_existing_install(
        self, tmp_path: Path, dual_install_venv: Path
    ) -> None:
        """sync() adds renamed packages without breaking existing installs."""
        from third_wheel.sync import sync

        # Create two versions of the same package
        v1_dir = tmp_path / "v1_wheels"
        v1_dir.mkdir()
        create_test_wheel(v1_dir, "mypkg", "1.0.0")

        v2_wheel = create_test_wheel(tmp_path, "mypkg", "2.0.0")

        # Step 1: Install mypkg v2.0.0 directly (simulating `uv sync`)
        install_wheel_in_venv(dual_install_venv, v2_wheel)

        # Verify v2 is importable
        result = run_in_venv(
            dual_install_venv,
            "import mypkg; print(mypkg.get_version())",
        )
        assert result.returncode == 0, f"v2 import failed: {result.stderr}"
        assert "2.0.0" in result.stdout

        # Step 2: Sync v1 as mypkg_v1 using find_links
        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        with patch(
            "third_wheel.sync.subprocess.run",
            side_effect=_make_mock_uv_pip_install(dual_install_venv),
        ):
            installed = sync(renames, find_links=v1_dir)

        assert len(installed) == 1
        assert "mypkg_v1" in installed[0].name

        # Step 3: Verify v2 is STILL importable (wasn't broken)
        result = run_in_venv(
            dual_install_venv,
            "import mypkg; print(mypkg.get_version())",
        )
        assert result.returncode == 0, f"v2 import broken after sync: {result.stderr}"
        assert "2.0.0" in result.stdout

        # Step 4: Verify v1 is importable under the new name
        result = run_in_venv(
            dual_install_venv,
            "import mypkg_v1; print(mypkg_v1.get_version())",
        )
        assert result.returncode == 0, f"v1 import failed: {result.stderr}"
        assert "1.0.0" in result.stdout

        # Step 5: Verify internal imports are isolated (no cross-contamination)
        isolation_code = textwrap.dedent("""\
            import mypkg.core as c2
            import mypkg_v1.core as c1

            assert c2.get_core_version() == "2.0.0", f"mypkg.core: {c2.get_core_version()}"
            assert c1.get_core_version() == "1.0.0", f"mypkg_v1.core: {c1.get_core_version()}"
            print("ISOLATED")
        """)
        result = run_in_venv(dual_install_venv, isolation_code)
        assert result.returncode == 0, f"Isolation check failed: {result.stderr}\n{result.stdout}"
        assert "ISOLATED" in result.stdout

    def test_sync_additive_with_multiple_renames(
        self, tmp_path: Path, dual_install_venv: Path
    ) -> None:
        """Multiple renames coexist with the original package."""
        from third_wheel.sync import sync

        # Create three versions
        wheels_dir = tmp_path / "wheels"
        wheels_dir.mkdir()
        create_test_wheel(wheels_dir, "mypkg", "1.0.0")
        create_test_wheel(wheels_dir, "mypkg", "2.0.0")

        v3_wheel = create_test_wheel(tmp_path, "mypkg", "3.0.0")

        # Install v3 directly
        install_wheel_in_venv(dual_install_venv, v3_wheel)

        # Sync v1 -> mypkg_v1 and v2 -> mypkg_v2
        renames = [
            RenameSpec("mypkg", "mypkg_v1", "<2"),
            RenameSpec("mypkg", "mypkg_v2", ">=2,<3"),
        ]

        with patch(
            "third_wheel.sync.subprocess.run",
            side_effect=_make_mock_uv_pip_install(dual_install_venv),
        ):
            installed = sync(renames, find_links=wheels_dir)

        assert len(installed) == 2

        # Verify all three versions coexist
        coexist_code = textwrap.dedent("""\
            import mypkg
            import mypkg_v1
            import mypkg_v2

            assert mypkg.get_version() == "3.0.0", f"mypkg: {mypkg.get_version()}"
            assert mypkg_v1.get_version() == "1.0.0", f"mypkg_v1: {mypkg_v1.get_version()}"
            assert mypkg_v2.get_version() == "2.0.0", f"mypkg_v2: {mypkg_v2.get_version()}"
            print("ALL_THREE")
        """)
        result = run_in_venv(dual_install_venv, coexist_code)
        assert result.returncode == 0, f"Coexistence failed: {result.stderr}\n{result.stdout}"
        assert "ALL_THREE" in result.stdout

    def test_sync_additive_repeated_is_idempotent(
        self, tmp_path: Path, dual_install_venv: Path
    ) -> None:
        """Running sync twice with the same rename doesn't break anything."""
        from third_wheel.sync import sync

        # Create wheels
        wheels_dir = tmp_path / "wheels"
        wheels_dir.mkdir()
        create_test_wheel(wheels_dir, "mypkg", "1.0.0")

        v2_wheel = create_test_wheel(tmp_path, "mypkg", "2.0.0")

        # Install v2 directly
        install_wheel_in_venv(dual_install_venv, v2_wheel)

        renames = [RenameSpec("mypkg", "mypkg_v1", "<2")]

        mock = _make_mock_uv_pip_install(dual_install_venv)

        # First sync
        with patch("third_wheel.sync.subprocess.run", side_effect=mock):
            installed1 = sync(renames, find_links=wheels_dir)

        assert len(installed1) == 1

        # Verify both work after first sync
        check_code = textwrap.dedent("""\
            import mypkg
            import mypkg_v1
            assert mypkg.get_version() == "2.0.0"
            assert mypkg_v1.get_version() == "1.0.0"
            print("OK")
        """)
        result = run_in_venv(dual_install_venv, check_code)
        assert result.returncode == 0, f"First sync check failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout

        # Second sync (same rename, should be idempotent)
        with patch("third_wheel.sync.subprocess.run", side_effect=mock):
            installed2 = sync(renames, find_links=wheels_dir)

        assert len(installed2) == 1

        # Verify both STILL work after second sync
        result = run_in_venv(dual_install_venv, check_code)
        assert result.returncode == 0, f"Second sync check failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# CLI tests: cache-clean
# ---------------------------------------------------------------------------


class TestCacheCleanCLI:
    """Test the ``third-wheel cache-clean`` CLI command."""

    @staticmethod
    def _populate_cache(root: Path) -> None:
        """Create a fake cache tree under *root* with sync/ and run/ subdirs."""
        sync_dir = root / "sync"
        sync_dir.mkdir(parents=True)
        (sync_dir / "numpy_v1-1.0-py3-none-any.whl").write_bytes(b"fake")

        run_dir = root / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "pandas_v1-2.0-py3-none-any.whl").write_bytes(b"fake")

    def test_cache_clean_removes_all(self, tmp_path: Path) -> None:
        """``cache-clean`` with no flags removes the entire cache directory."""
        fake_cache = tmp_path / "cache"
        self._populate_cache(fake_cache)

        runner = CliRunner()
        with patch("third_wheel.run.cache_dir", return_value=fake_cache):
            result = runner.invoke(main, ["cache-clean"])

        assert result.exit_code == 0
        assert not fake_cache.exists()

    def test_cache_clean_sync_only(self, tmp_path: Path) -> None:
        """``cache-clean --sync-only`` removes only the sync/ subdirectory."""
        fake_cache = tmp_path / "cache"
        self._populate_cache(fake_cache)

        runner = CliRunner()
        with patch("third_wheel.run.cache_dir", return_value=fake_cache):
            result = runner.invoke(main, ["cache-clean", "--sync-only"])

        assert result.exit_code == 0
        assert not (fake_cache / "sync").exists()
        # run/ should still be there
        assert (fake_cache / "run").exists()

    def test_cache_clean_run_only(self, tmp_path: Path) -> None:
        """``cache-clean --run-only`` removes non-sync dirs, preserves sync/."""
        fake_cache = tmp_path / "cache"
        self._populate_cache(fake_cache)

        runner = CliRunner()
        with patch("third_wheel.run.cache_dir", return_value=fake_cache):
            result = runner.invoke(main, ["cache-clean", "--run-only"])

        assert result.exit_code == 0
        # sync/ should still be there
        assert (fake_cache / "sync").exists()
        assert (fake_cache / "sync" / "numpy_v1-1.0-py3-none-any.whl").exists()
        # run/ should be gone
        assert not (fake_cache / "run").exists()

    def test_cache_clean_no_cache_exists(self, tmp_path: Path) -> None:
        """When cache dir doesn't exist, prints message and exits cleanly."""
        fake_cache = tmp_path / "nonexistent"

        runner = CliRunner()
        with patch("third_wheel.run.cache_dir", return_value=fake_cache):
            result = runner.invoke(main, ["cache-clean"])

        assert result.exit_code == 0
        assert (
            "nothing to clean" in result.output.lower() or "does not exist" in result.output.lower()
        )

    def test_cache_clean_verbose(self, tmp_path: Path) -> None:
        """``cache-clean -v`` prints details about what was removed."""
        fake_cache = tmp_path / "cache"
        self._populate_cache(fake_cache)

        runner = CliRunner()
        with patch("third_wheel.run.cache_dir", return_value=fake_cache):
            result = runner.invoke(main, ["cache-clean", "-v"])

        assert result.exit_code == 0
        assert "wheel" in result.output.lower()
        assert not fake_cache.exists()


# ---------------------------------------------------------------------------
# Pixi integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPixiIntegration:
    """Test third-wheel sync inside a pixi environment.

    These tests require pixi to be installed and create real pixi environments.
    They verify that the auto-detection logic correctly identifies pixi envs
    and uses ``uv pip install --python`` to target the conda env.
    """

    @staticmethod
    def _pixi_available() -> bool:
        import subprocess as sp

        try:
            sp.run(["pixi", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, sp.CalledProcessError):
            return False
        return True

    @pytest.fixture
    def pixi_env(self, tmp_path: Path) -> Path:
        """Create a fresh pixi environment with Python and pip."""
        import subprocess as sp

        if not self._pixi_available():
            pytest.skip("pixi not installed")

        project_dir = tmp_path / "pixi-project"
        project_dir.mkdir()

        # Write pixi.toml
        pixi_toml = project_dir / "pixi.toml"
        pixi_toml.write_text(
            textwrap.dedent("""\
            [workspace]
            name = "tw-test"
            version = "0.1.0"
            channels = ["conda-forge"]
            platforms = ["osx-arm64", "osx-64", "linux-64"]

            [dependencies]
            python = ">=3.11"
            pip = "*"
        """)
        )

        # Install the pixi environment
        result = sp.run(
            ["pixi", "install"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"pixi install failed: {result.stderr}")

        return project_dir

    def _pixi_run(
        self,
        pixi_dir: Path,
        cmd: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command inside the pixi environment."""
        return subprocess.run(
            ["pixi", "run", *cmd],
            cwd=pixi_dir,
            capture_output=True,
            text=True,
            **kwargs,  # type: ignore[arg-type]
        )

    def _pixi_python(self, pixi_dir: Path) -> Path:
        """Get the Python executable path for the pixi env."""
        result = self._pixi_run(
            pixi_dir,
            ["python", "-c", "import sys; print(sys.executable)"],
        )
        assert result.returncode == 0, f"Cannot find pixi python: {result.stderr}"
        return Path(result.stdout.strip())

    def test_auto_detect_pixi_env(self, pixi_env: Path) -> None:
        """_detect_installer() uses uv pip install --python in a pixi env."""
        code = (
            "from third_wheel.sync import _detect_installer; cmd = _detect_installer(); print(cmd)"
        )
        result = self._pixi_run(pixi_env, ["python", "-c", code])
        # If third-wheel isn't importable in the pixi env, install it
        if result.returncode != 0:
            self._pixi_run(
                pixi_env,
                ["pip", "install", "-e", str(Path(__file__).parent.parent)],
            )
            result = self._pixi_run(pixi_env, ["python", "-c", code])
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should use uv pip install --python <conda_python>
        assert "--python" in result.stdout

    def test_sync_in_pixi_env(self, tmp_path: Path, pixi_env: Path) -> None:
        """Full end-to-end: sync a renamed package inside a pixi env."""
        # Install third-wheel into pixi env
        tw_root = Path(__file__).parent.parent
        self._pixi_run(pixi_env, ["pip", "install", "-e", str(tw_root)])

        # Create test wheels
        v1_dir = tmp_path / "v1_wheels"
        v1_dir.mkdir()
        create_test_wheel(v1_dir, "mypkg", "1.0.0")

        v2_wheel = create_test_wheel(tmp_path, "mypkg", "2.0.0")

        # Install v2 directly
        self._pixi_run(pixi_env, ["pip", "install", str(v2_wheel)])

        # Verify v2 works
        result = self._pixi_run(
            pixi_env,
            ["python", "-c", "import mypkg; print(mypkg.get_version())"],
        )
        assert result.returncode == 0, f"v2 import failed: {result.stderr}"
        assert "2.0.0" in result.stdout

        # Run third-wheel sync inside pixi
        result = self._pixi_run(
            pixi_env,
            [
                "third-wheel",
                "sync",
                "--find-links",
                str(v1_dir),
                "--rename",
                "mypkg<2=mypkg_v1",
                "-v",
            ],
        )
        assert result.returncode == 0, f"sync failed: {result.stderr}\n{result.stdout}"
        assert "Synced" in result.stdout or "Installed" in result.stdout

        # Verify both versions work
        check_code = (
            "import mypkg; import mypkg_v1; "
            "assert mypkg.get_version() == '2.0.0', mypkg.get_version(); "
            "assert mypkg_v1.get_version() == '1.0.0', mypkg_v1.get_version(); "
            "print('PASS')"
        )
        result = self._pixi_run(pixi_env, ["python", "-c", check_code])
        assert result.returncode == 0, f"Dual import failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout
