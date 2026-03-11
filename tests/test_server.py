"""Tests for the proxy server application."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from third_wheel.server.app import create_app
from third_wheel.server.config import PatchRule, ProxyConfig, RenameRule
from third_wheel.server.html import generate_project_index
from third_wheel.server.stream import original_filename_from_renamed, rewrite_wheel_filename
from third_wheel.server.upstream import UpstreamClient

# ---------------------------------------------------------------------------
# HTML generation tests
# ---------------------------------------------------------------------------


class TestGenerateProjectIndex:
    """Test PEP 503 HTML generation."""

    def test_basic_index(self) -> None:
        packages = [
            {"filename": "pkg-1.0.0-py3-none-any.whl", "url": "https://example.com/pkg.whl"},
        ]
        html = generate_project_index("pkg", packages)
        assert "Links for pkg" in html
        assert "pkg-1.0.0-py3-none-any.whl" in html

    def test_hash_included_for_normal_packages(self) -> None:
        packages = [
            {
                "filename": "pkg-1.0.0-py3-none-any.whl",
                "url": "https://example.com/pkg.whl",
                "hash": "sha256=abc123",
                "requires_python": None,
            },
        ]
        html = generate_project_index("pkg", packages)
        assert "sha256=abc123" in html

    def test_hash_stripped_for_renamed_packages(self) -> None:
        """Renamed packages have different content, so hashes must be stripped."""
        packages = [
            {
                "filename": "zarr-2.18.0-py3-none-any.whl",
                "url": "https://example.com/zarr.whl",
                "hash": "sha256=abc123",
                "requires_python": None,
            },
        ]
        rule = RenameRule(original="zarr", new_name="zarr_v2")
        html = generate_project_index("zarr_v2", packages, rename_rule=rule)
        # Hash should NOT be present (content changes after rename)
        assert "sha256=abc123" not in html
        # But the renamed filename should be
        assert "zarr_v2-2.18.0-py3-none-any.whl" in html

    def test_hash_stripped_when_strip_hashes_flag(self) -> None:
        """Patched packages use strip_hashes=True to omit upstream hashes."""
        packages = [
            {
                "filename": "pkg-1.0.0-py3-none-any.whl",
                "url": "https://example.com/pkg.whl",
                "hash": "sha256=abc123",
                "requires_python": None,
            },
        ]
        html = generate_project_index("pkg", packages, strip_hashes=True)
        assert "sha256=abc123" not in html

    def test_requires_python_attribute(self) -> None:
        packages = [
            {
                "filename": "pkg-1.0.0-py3-none-any.whl",
                "url": "https://example.com/pkg.whl",
                "requires_python": ">=3.8",
                "hash": None,
            },
        ]
        html = generate_project_index("pkg", packages)
        assert 'data-requires-python="&gt;=3.8"' in html


# ---------------------------------------------------------------------------
# Filename rewriting tests
# ---------------------------------------------------------------------------


class TestRewriteWheelFilename:
    def test_basic_rewrite(self) -> None:
        result = rewrite_wheel_filename("zarr-2.18.0-py3-none-any.whl", "zarr", "zarr_v2")
        assert result == "zarr_v2-2.18.0-py3-none-any.whl"

    def test_no_match(self) -> None:
        result = rewrite_wheel_filename("numpy-1.24.0-py3-none-any.whl", "zarr", "zarr_v2")
        assert result == "numpy-1.24.0-py3-none-any.whl"


class TestOriginalFilenameFromRenamed:
    def test_basic_reverse(self) -> None:
        result = original_filename_from_renamed(
            "zarr_v2-2.18.0-py3-none-any.whl", "zarr", "zarr_v2"
        )
        assert result == "zarr-2.18.0-py3-none-any.whl"

    def test_no_match(self) -> None:
        result = original_filename_from_renamed("numpy-1.0.0-py3-none-any.whl", "zarr", "zarr_v2")
        assert result == "numpy-1.0.0-py3-none-any.whl"


# ---------------------------------------------------------------------------
# Helpers for server tests
# ---------------------------------------------------------------------------


def _make_test_wheel_bytes(pkg_name: str = "testpkg", dep_name: str = "zarr") -> bytes:
    """Create a minimal wheel in memory that imports a dependency."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"{pkg_name}/__init__.py",
            f"import {dep_name}\n__version__ = '1.0.0'\n",
        )
        zf.writestr(
            f"{pkg_name}-1.0.0.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {pkg_name}\nVersion: 1.0.0\n",
        )
        zf.writestr(
            f"{pkg_name}-1.0.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        zf.writestr(f"{pkg_name}-1.0.0.dist-info/RECORD", "")
    return buf.getvalue()


def _make_upstream_packages(
    pkg_name: str = "testpkg",
    version: str = "1.0.0",
    url: str = "https://files.example.com/testpkg-1.0.0-py3-none-any.whl",
) -> list[dict[str, str | None]]:
    """Create a list of package dicts as returned by UpstreamClient.get_project_page."""
    return [
        {
            "filename": f"{pkg_name}-{version}-py3-none-any.whl",
            "url": url,
            "requires_python": ">=3.8",
            "hash": "sha256=deadbeef",
        }
    ]


def _mock_upstream_client(
    upstream_packages: list[dict[str, str | None]],
    download_bytes: bytes | None = None,
):
    """Return a stack of mock context managers for UpstreamClient.

    Patches __aenter__ to return the UpstreamClient instance itself (so the
    lifespan properly initializes), plus get_project_page and optionally
    download_wheel.
    """
    from contextlib import ExitStack

    stack = ExitStack()

    # __aenter__ must return the instance for `async with upstream_client:` to work
    async def _aenter(self):
        return self

    stack.enter_context(patch.object(UpstreamClient, "__aenter__", _aenter))
    stack.enter_context(
        patch.object(UpstreamClient, "__aexit__", new_callable=AsyncMock, return_value=None)
    )
    stack.enter_context(
        patch.object(
            UpstreamClient,
            "get_project_page",
            new_callable=AsyncMock,
            return_value=upstream_packages,
        )
    )

    if download_bytes is not None:
        stack.enter_context(
            patch.object(
                UpstreamClient,
                "download_wheel",
                new_callable=AsyncMock,
                return_value=download_bytes,
            )
        )

    return stack


# ---------------------------------------------------------------------------
# Server endpoint tests
# ---------------------------------------------------------------------------


class TestServerRootIndex:
    """Test the /simple/ root index."""

    def test_root_redirects(self) -> None:
        config = ProxyConfig(upstreams=["https://pypi.org/simple/"])
        app = create_app(config)
        with TestClient(app) as client:
            resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/simple/" in resp.headers["location"]

    def test_simple_index_lists_virtual_packages(self) -> None:
        config = ProxyConfig(
            upstreams=["https://pypi.org/simple/"],
            renames=[RenameRule(original="zarr", new_name="zarr_v2")],
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")],
        )
        app = create_app(config)
        with TestClient(app) as client:
            resp = client.get("/simple/")
        assert resp.status_code == 200
        assert "zarr_v2" in resp.text
        assert "anemoi-datasets" in resp.text


class TestServerPatchEndpoints:
    """Test proxy endpoints with patch rules."""

    def test_project_index_for_patched_package(self) -> None:
        """Project index for a patched package should strip hashes."""
        config = ProxyConfig(
            upstreams=["https://pypi.org/simple/"],
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")],
        )
        app = create_app(config)

        upstream_packages = _make_upstream_packages(
            "anemoi_datasets",
            "0.5.31",
            "https://files.example.com/anemoi_datasets-0.5.31-py3-none-any.whl",
        )

        with _mock_upstream_client(upstream_packages), TestClient(app) as client:
            resp = client.get("/simple/anemoi-datasets/")

        assert resp.status_code == 200
        # Hash should be stripped (content will change after patching)
        assert "sha256=deadbeef" not in resp.text
        # Filename should still be present
        assert "anemoi_datasets-0.5.31-py3-none-any.whl" in resp.text

    def test_download_patched_wheel(self) -> None:
        """Downloading a patched package should return patched content."""
        config = ProxyConfig(
            upstreams=["https://pypi.org/simple/"],
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")],
        )
        app = create_app(config)

        wheel_bytes = _make_test_wheel_bytes("anemoi_datasets", "zarr")
        upstream_packages = _make_upstream_packages(
            "anemoi_datasets",
            "0.5.31",
            "https://files.example.com/anemoi_datasets-0.5.31-py3-none-any.whl",
        )

        with (
            _mock_upstream_client(upstream_packages, download_bytes=wheel_bytes),
            TestClient(app) as client,
        ):
            resp = client.get("/simple/anemoi-datasets/anemoi_datasets-0.5.31-py3-none-any.whl")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"

        # Verify the downloaded wheel is patched
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            init = zf.read("anemoi_datasets/__init__.py").decode()
            assert "import zarr_v2" in init
            assert "import zarr\n" not in init


class TestServerRenameEndpoints:
    """Test proxy endpoints with rename rules (verify hash fix)."""

    def test_project_index_strips_hash_for_renamed(self) -> None:
        """Renamed packages should not include upstream hashes."""
        config = ProxyConfig(
            upstreams=["https://pypi.org/simple/"],
            renames=[RenameRule(original="zarr", new_name="zarr_v2", version_spec="<=2.18.7")],
        )
        app = create_app(config)

        upstream_packages = _make_upstream_packages(
            "zarr",
            "2.18.0",
            "https://files.example.com/zarr-2.18.0-py3-none-any.whl",
        )

        with _mock_upstream_client(upstream_packages), TestClient(app) as client:
            resp = client.get("/simple/zarr-v2/")

        assert resp.status_code == 200
        # Hash must NOT appear (the rename changes content)
        assert "sha256=deadbeef" not in resp.text
        # Renamed filename should appear
        assert "zarr_v2-2.18.0-py3-none-any.whl" in resp.text
