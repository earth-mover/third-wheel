"""Upstream index client for the proxy server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from packaging.specifiers import SpecifierSet
from packaging.version import Version

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from third_wheel.server.config import ProxyConfig, RenameRule


class UpstreamClient:
    """Client for querying upstream package indexes."""

    def __init__(self, config: ProxyConfig) -> None:
        """Initialize the upstream client.

        Args:
            config: Proxy configuration with upstream URLs
        """
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> UpstreamClient:
        """Enter async context."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if self._client is None:
            msg = "Client not initialized. Use 'async with' context manager."
            raise RuntimeError(msg)
        return self._client

    async def get_project_page(
        self,
        project: str,
        rename_rule: RenameRule | None = None,
    ) -> list[dict[str, str | None]]:
        """Fetch and parse a project page from upstream.

        Args:
            project: Project name to look up
            rename_rule: If set, filter packages by version constraint

        Returns:
            List of package dicts with filename, url, requires_python, hash
        """
        from pypi_simple import ProjectPage

        # Try each upstream in order
        for upstream_url in self.config.upstreams:
            url = f"{upstream_url.rstrip('/')}/{project}/"

            try:
                response = await self.client.get(url)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Upstream %s failed for %s: %s", upstream_url, project, exc)
                continue

            # Parse the HTML response
            page = ProjectPage.from_html(project, response.text, upstream_url)
            packages = []

            # Filter by version if we have a rename rule with version spec
            version_spec = None
            if rename_rule and rename_rule.version_spec:
                version_spec = SpecifierSet(rename_rule.version_spec, prereleases=True)

            for pkg in page.packages:
                # Only include wheels
                if pkg.package_type != "wheel":
                    continue

                # Filter by version if specified
                if version_spec and pkg.version:
                    try:
                        if Version(pkg.version) not in version_spec:
                            continue
                    except (ValueError, TypeError):
                        # Skip packages with unparseable versions
                        continue

                # Build package info dict
                pkg_info: dict[str, str | None] = {
                    "filename": pkg.filename,
                    "url": pkg.url,
                    "requires_python": pkg.requires_python,
                    "hash": None,
                }

                # Extract hash if available
                if pkg.digests:
                    for algo in ("sha256", "sha384", "sha512", "md5"):
                        if algo in pkg.digests:
                            pkg_info["hash"] = f"{algo}={pkg.digests[algo]}"
                            break

                packages.append(pkg_info)

            return packages

        # No upstream had the project
        return []

    async def stream_wheel(self, url: str) -> AsyncIterator[bytes]:
        """Stream wheel bytes from an upstream URL.

        Args:
            url: Full URL to the wheel file

        Yields:
            Chunks of wheel bytes
        """
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    async def download_wheel(self, url: str) -> bytes:
        """Download a complete wheel from upstream.

        Args:
            url: Full URL to the wheel file

        Returns:
            Complete wheel bytes
        """
        chunks = []
        async for chunk in self.stream_wheel(url):
            chunks.append(chunk)
        return b"".join(chunks)

    def find_package_url(
        self,
        packages: list[dict[str, str | None]],
        original_filename: str,
    ) -> str | None:
        """Find the upstream URL for a package by its original filename.

        Args:
            packages: List of package dicts
            original_filename: The original (non-renamed) filename to find

        Returns:
            URL to download the package, or None if not found
        """
        for pkg in packages:
            if pkg["filename"] == original_filename:
                return pkg["url"]
        return None
