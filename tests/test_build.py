"""Tests for third_wheel.build module.

Covers building wheels from git URLs and local filesystem paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from third_wheel.build import build_wheel_from_source


class TestBuildWheelFromSource:
    """Test build_wheel_from_source with mocked subprocess."""

    def test_successful_build(self, tmp_path: Path) -> None:
        """A successful build returns the path to the new wheel."""
        wheel_name = "mypkg-1.0.0-py3-none-any.whl"
        fake_wheel = tmp_path / wheel_name

        def create_wheel(*_args: Any, **_kwargs: Any) -> MagicMock:
            fake_wheel.write_bytes(b"fake wheel content")
            result = MagicMock()
            result.returncode = 0
            result.stdout = "Built mypkg-1.0.0"
            result.stderr = ""
            return result

        with patch("third_wheel.build.subprocess.run", side_effect=create_wheel) as mock_run:
            result = build_wheel_from_source("git+https://github.com/org/repo@main", tmp_path)

        assert result == fake_wheel
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["uv", "pip", "wheel"]
        assert "git+https://github.com/org/repo@main" in cmd
        assert "--no-deps" in cmd
        assert str(tmp_path) in cmd

    def test_build_failure_raises(self, tmp_path: Path) -> None:
        """A failed build raises RuntimeError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "build error details"

        with (
            patch("third_wheel.build.subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="Failed to build wheel"),
        ):
            build_wheel_from_source("git+https://github.com/org/repo@main", tmp_path)

    def test_no_wheel_produced_returns_none(self, tmp_path: Path) -> None:
        """If the build succeeds but no wheel is created, returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""

        with patch("third_wheel.build.subprocess.run", return_value=mock_result):
            result = build_wheel_from_source("git+https://github.com/org/repo@main", tmp_path)

        assert result is None

    def test_ignores_preexisting_wheels(self, tmp_path: Path) -> None:
        """Pre-existing wheels in the output dir are not returned."""
        existing = tmp_path / "existing-1.0.0-py3-none-any.whl"
        existing.write_bytes(b"old wheel")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("third_wheel.build.subprocess.run", return_value=mock_result):
            result = build_wheel_from_source("git+https://github.com/org/repo@main", tmp_path)

        assert result is None

    def test_local_path_source(self, tmp_path: Path) -> None:
        """Local path source is passed directly to uv pip wheel."""
        wheel_name = "localpkg-0.1.0-py3-none-any.whl"
        fake_wheel = tmp_path / wheel_name

        def create_wheel(*_args: Any, **_kwargs: Any) -> MagicMock:
            fake_wheel.write_bytes(b"fake wheel")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("third_wheel.build.subprocess.run", side_effect=create_wheel) as mock_run:
            result = build_wheel_from_source("/some/local/path", tmp_path)

        assert result == fake_wheel
        cmd = mock_run.call_args[0][0]
        assert "/some/local/path" in cmd

    def test_returns_sorted_first_if_multiple_wheels(self, tmp_path: Path) -> None:
        """If multiple new wheels appear, returns the first (sorted)."""

        def create_wheels(*_args: Any, **_kwargs: Any) -> MagicMock:
            (tmp_path / "a_pkg-1.0.0-py3-none-any.whl").write_bytes(b"a")
            (tmp_path / "b_pkg-1.0.0-py3-none-any.whl").write_bytes(b"b")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("third_wheel.build.subprocess.run", side_effect=create_wheels):
            result = build_wheel_from_source("git+https://example.com/repo", tmp_path)

        assert result is not None
        assert result.name == "a_pkg-1.0.0-py3-none-any.whl"
