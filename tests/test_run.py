"""Tests for third_wheel.run module."""

from __future__ import annotations

from pathlib import Path

import pytest

from third_wheel.run import (
    RenameSpec,
    _print_run_dry_run,
    extract_renames_from_comments,
    extract_renames_from_tool_table,
    merge_renames,
    parse_all_renames,
    parse_cli_renames,
    parse_pep723_metadata,
    rewrite_script_metadata,
    run_script,
)


class TestParsePEP723Metadata:
    def test_basic_metadata(self):
        script = """\
# /// script
# dependencies = [
#   "requests",
# ]
# ///
import requests
"""
        result = parse_pep723_metadata(script)
        assert result is not None
        assert '"requests"' in result

    def test_no_metadata(self):
        script = "import sys\nprint('hello')\n"
        assert parse_pep723_metadata(script) is None

    def test_metadata_with_tool_section(self):
        script = """\
# /// script
# dependencies = [
#   "icechunk_v1",
# ]
# [tool.third-wheel]
# renames = [
#   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
# ]
# ///
"""
        result = parse_pep723_metadata(script)
        assert result is not None
        assert "tool.third-wheel" in result
        assert "icechunk" in result

    def test_empty_metadata(self):
        script = """\
# /// script
# ///
"""
        assert parse_pep723_metadata(script) is None


class TestExtractRenamesFromComments:
    def test_basic_rename_comment(self):
        toml_str = """\
dependencies = [
  "icechunk_v1",  # icechunk<2
  "icechunk>=2",
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version == "<2"

    def test_spaced_version(self):
        toml_str = """\
dependencies = [
  "icechunk_v1",  # icechunk < 2
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].version == "< 2"

    def test_complex_version_spec(self):
        toml_str = """\
dependencies = [
  "zarr_v2",  # zarr>=2.0,<3
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "zarr"
        assert renames[0].new_name == "zarr_v2"
        assert renames[0].version == ">=2.0,<3"

    def test_no_version(self):
        toml_str = """\
dependencies = [
  "my_requests",  # requests
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "requests"
        assert renames[0].new_name == "my_requests"
        assert renames[0].version is None

    def test_no_rename_comments(self):
        toml_str = """\
dependencies = [
  "requests",
  "numpy>=1.0",
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 0

    def test_multiple_renames(self):
        toml_str = """\
dependencies = [
  "icechunk_v1",  # icechunk<2
  "zarr_v2",  # zarr<3
  "requests",
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 2
        names = {r.new_name for r in renames}
        assert names == {"icechunk_v1", "zarr_v2"}

    def test_single_quotes(self):
        toml_str = """\
dependencies = [
  'icechunk_v1',  # icechunk<2
]
"""
        renames = extract_renames_from_comments(toml_str)
        assert len(renames) == 1
        assert renames[0].new_name == "icechunk_v1"


class TestExtractRenamesFromToolTable:
    def test_basic_tool_table(self):
        toml_str = """\
dependencies = [
  "icechunk_v1",
]
[tool.third-wheel]
renames = [
  {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
]
"""
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version == "<2"

    def test_multiple_renames(self):
        toml_str = """\
[tool.third-wheel]
renames = [
  {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
  {original = "zarr", new-name = "zarr_v2", version = "<3"},
]
"""
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 2

    def test_no_tool_table(self):
        toml_str = 'dependencies = ["requests"]'
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 0

    def test_no_version(self):
        toml_str = """\
[tool.third-wheel]
renames = [
  {original = "requests", new-name = "my_requests"},
]
"""
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 1
        assert renames[0].version is None

    def test_with_source_field(self):
        toml_str = """\
[tool.third-wheel]
renames = [
  {original = "zarr", new-name = "zarr_dev", source = "git+https://github.com/zarr-developers/zarr-python@main"},
]
"""
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 1
        assert renames[0].original == "zarr"
        assert renames[0].new_name == "zarr_dev"
        assert renames[0].source == "git+https://github.com/zarr-developers/zarr-python@main"
        assert renames[0].version is None

    def test_with_source_and_version(self):
        toml_str = """\
[tool.third-wheel]
renames = [
  {original = "zarr", new-name = "zarr_dev", version = ">=3", source = "git+https://github.com/zarr-developers/zarr-python@main"},
]
"""
        renames = extract_renames_from_tool_table(toml_str)
        assert len(renames) == 1
        assert renames[0].source == "git+https://github.com/zarr-developers/zarr-python@main"
        assert renames[0].version == ">=3"

    def test_invalid_toml(self):
        renames = extract_renames_from_tool_table("this is not valid toml {{{")
        assert len(renames) == 0


class TestParseAllRenames:
    def test_comment_only(self):
        script = """\
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2",
# ]
# ///
"""
        renames = parse_all_renames(script)
        assert len(renames) == 1
        assert renames[0].new_name == "icechunk_v1"

    def test_tool_table_only(self):
        script = """\
# /// script
# dependencies = [
#   "icechunk_v1",
# ]
# [tool.third-wheel]
# renames = [
#   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
# ]
# ///
"""
        renames = parse_all_renames(script)
        assert len(renames) == 1
        assert renames[0].new_name == "icechunk_v1"

    def test_tool_table_wins_over_comment(self):
        script = """\
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<3
# ]
# [tool.third-wheel]
# renames = [
#   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
# ]
# ///
"""
        renames = parse_all_renames(script)
        assert len(renames) == 1
        # Tool table version wins
        assert renames[0].version == "<2"

    def test_no_metadata(self):
        script = "import sys\n"
        assert parse_all_renames(script) == []


class TestParseCLIRenames:
    def test_basic(self):
        renames = parse_cli_renames(["icechunk<2=icechunk_v1"])
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version == "<2"

    def test_no_version(self):
        renames = parse_cli_renames(["icechunk=icechunk_v1"])
        assert len(renames) == 1
        assert renames[0].original == "icechunk"
        assert renames[0].new_name == "icechunk_v1"
        assert renames[0].version is None

    def test_complex_version(self):
        renames = parse_cli_renames(["zarr>=2.0,<3=zarr_v2"])
        assert len(renames) == 1
        assert renames[0].original == "zarr"
        assert renames[0].version == ">=2.0,<3"
        assert renames[0].new_name == "zarr_v2"

    def test_multiple(self):
        renames = parse_cli_renames(["icechunk<2=icechunk_v1", "zarr<3=zarr_v2"])
        assert len(renames) == 2

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid --rename format"):
            parse_cli_renames(["not-valid-format"])

    def test_empty(self):
        assert parse_cli_renames([]) == []


class TestMergeRenames:
    def test_cli_overrides_script(self):
        script_renames = [RenameSpec("icechunk", "icechunk_v1", "<3")]
        cli_renames = [RenameSpec("icechunk", "icechunk_v1", "<2")]
        merged = merge_renames(script_renames, cli_renames)
        assert len(merged) == 1
        assert merged[0].version == "<2"  # CLI wins

    def test_combines_different(self):
        script_renames = [RenameSpec("icechunk", "icechunk_v1", "<2")]
        cli_renames = [RenameSpec("zarr", "zarr_v2", "<3")]
        merged = merge_renames(script_renames, cli_renames)
        assert len(merged) == 2

    def test_empty(self):
        assert merge_renames([], []) == []


class TestRewriteScriptMetadata:
    def test_strips_rename_comments(self):
        script = """\
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2",
#   "requests",
# ]
# ///
import icechunk_v1
"""
        renames = [RenameSpec("icechunk", "icechunk_v1", "<2")]
        result = rewrite_script_metadata(script, renames)
        # The rename comment should be stripped
        assert "# icechunk<2" not in result
        # But the dependency should still be there
        assert '"icechunk_v1"' in result
        # Non-renamed deps should be untouched
        assert '"icechunk>=2"' in result
        assert '"requests"' in result
        # Code section should be untouched
        assert "import icechunk_v1" in result

    def test_no_changes_without_renames(self):
        script = """\
# /// script
# dependencies = [
#   "requests",
# ]
# ///
"""
        result = rewrite_script_metadata(script, [])
        assert result == script


class TestRenameSpec:
    def test_version_spec_with_version(self):
        spec = RenameSpec("icechunk", "icechunk_v1", "<2")
        assert spec.version_spec == "icechunk<2"

    def test_version_spec_without_version(self):
        spec = RenameSpec("icechunk", "icechunk_v1")
        assert spec.version_spec == "icechunk"

    def test_source_type_index_when_no_source(self):
        spec = RenameSpec("icechunk", "icechunk_v1", "<2")
        assert spec.source_type == "index"

    def test_source_type_git(self):
        spec = RenameSpec("zarr", "zarr_dev", source="git+https://github.com/org/repo@main")
        assert spec.source_type == "git"

    def test_source_type_path(self):
        spec = RenameSpec("zarr", "zarr_dev", source="/home/user/zarr-python")
        assert spec.source_type == "path"

    def test_source_type_path_relative(self):
        spec = RenameSpec("zarr", "zarr_dev", source="./zarr-python")
        assert spec.source_type == "path"

    def test_source_field_default_none(self):
        spec = RenameSpec("icechunk", "icechunk_v1")
        assert spec.source is None


class TestRunScriptDryRun:
    """Tests for dry_run mode in run_script."""

    def test_dry_run_no_renames(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """dry_run with no renames prints message and returns 0."""
        script = tmp_path / "test.py"
        script.write_text("print('hello')\n")
        result = run_script(script, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "No renames detected" in captured.err
        assert "Would run:" in captured.err

    def test_dry_run_with_renames(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """dry_run with renames shows rename table, cache status, and command."""
        script = tmp_path / "test.py"
        script.write_text("""\
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2",
# ]
# ///
print('hello')
""")
        result = run_script(script, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "icechunk" in captured.err
        assert "icechunk_v1" in captured.err
        assert "Cache:" in captured.err
        assert "Would run:" in captured.err

    def test_dry_run_with_cli_renames(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """dry_run shows CLI renames with correct source label."""
        script = tmp_path / "test.py"
        script.write_text("print('hello')\n")
        cli_renames = [RenameSpec("requests", "requests_old", "<2")]
        result = run_script(script, cli_renames=cli_renames, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "requests" in captured.err
        assert "CLI" in captured.err

    def test_dry_run_does_not_create_cache_dir(self, tmp_path: Path) -> None:
        """dry_run should not create any cache directories."""
        import os

        os.environ["THIRD_WHEEL_CACHE_DIR"] = str(tmp_path / "cache")
        try:
            script = tmp_path / "test.py"
            script.write_text("""\
# /// script
# dependencies = [
#   "icechunk_v1",  # icechunk<2
# ]
# ///
print('hello')
""")
            run_script(script, dry_run=True)
            # The cache dir should not have been created by dry_run
            cache_wheels = tmp_path / "cache"
            # cache_dir itself might not exist, or if it does, no wheels subdir
            if cache_wheels.exists():
                assert not list(cache_wheels.rglob("*.whl"))
        finally:
            del os.environ["THIRD_WHEEL_CACHE_DIR"]

    def test_dry_run_shows_source_type(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """dry_run shows source type for git/path sources."""
        script = tmp_path / "test.py"
        script.write_text("print('hello')\n")
        cli_renames = [
            RenameSpec("zarr", "zarr_dev", source="git+https://github.com/org/repo@main"),
        ]
        result = run_script(script, cli_renames=cli_renames, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "git" in captured.err


class TestPrintRunDryRun:
    """Tests for the _print_run_dry_run helper."""

    def test_cache_hit(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Shows cache HIT when expected wheels exist."""
        wheel_dir = tmp_path / "wheels"
        wheel_dir.mkdir()
        (wheel_dir / "icechunk_v1-1.0.0-py3-none-any.whl").touch()

        renames = [RenameSpec("icechunk", "icechunk_v1", "<2")]
        _print_run_dry_run(
            renames,
            [],
            index_url="https://pypi.org/simple/",
            python_version=None,
            wheel_dir=wheel_dir,
            script_path=Path("test.py"),
            script_args=None,
        )
        captured = capsys.readouterr()
        assert "Cache: HIT" in captured.err

    def test_cache_miss(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Shows cache MISS when wheel dir doesn't exist."""
        wheel_dir = tmp_path / "nonexistent"
        renames = [RenameSpec("icechunk", "icechunk_v1", "<2")]
        _print_run_dry_run(
            renames,
            [],
            index_url="https://pypi.org/simple/",
            python_version=None,
            wheel_dir=wheel_dir,
            script_path=Path("test.py"),
            script_args=None,
        )
        captured = capsys.readouterr()
        assert "Cache: MISS" in captured.err

    def test_path_source_cache_skip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Shows cache SKIP for path sources."""
        wheel_dir = tmp_path / "wheels"
        wheel_dir.mkdir()
        (wheel_dir / "zarr_dev-1.0.0-py3-none-any.whl").touch()

        renames = [RenameSpec("zarr", "zarr_dev", source="/path/to/zarr")]
        _print_run_dry_run(
            renames,
            [],
            index_url="https://pypi.org/simple/",
            python_version=None,
            wheel_dir=wheel_dir,
            script_path=Path("test.py"),
            script_args=None,
        )
        captured = capsys.readouterr()
        assert "Cache: SKIP" in captured.err
