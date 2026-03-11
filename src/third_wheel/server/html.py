"""PEP 503 HTML generation for the proxy server."""

from __future__ import annotations

import html as html_lib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from third_wheel.server.config import RenameRule


def generate_root_index(projects: list[str]) -> str:
    """Generate the root /simple/ HTML page listing all projects.

    Args:
        projects: List of project names to include

    Returns:
        PEP 503 compliant HTML
    """
    links = "\n".join(
        f'    <a href="{html_lib.escape(project, quote=True)}/">{html_lib.escape(project)}</a>'
        for project in sorted(set(projects))
    )
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Simple Index</title>
</head>
<body>
{links}
</body>
</html>
"""


def generate_project_index(
    project: str,
    packages: list[dict[str, str | None]],
    rename_rule: RenameRule | None = None,
    *,
    strip_hashes: bool = False,
) -> str:
    """Generate the project page HTML listing all wheels.

    Args:
        project: Project name (may be renamed)
        packages: List of package dicts with 'filename', 'url', 'requires_python', 'hash'
        rename_rule: If set, rewrite filenames from original to new name
        strip_hashes: If True, omit hash metadata (for patched packages whose content changes)

    Returns:
        PEP 503 compliant HTML
    """
    links = []
    for pkg in packages:
        filename = pkg["filename"]
        url = pkg.get("url", filename)

        # If this is a renamed package, rewrite the filename
        if rename_rule is not None:
            # Replace original name with new name in filename
            # e.g., icechunk-1.0.0-... -> icechunk_v1-1.0.0-...
            filename = filename.replace(f"{rename_rule.original}-", f"{rename_rule.new_name}-", 1)
            # URL points to ourselves for download (we'll rename on-the-fly)
            url = filename

        # Build anchor attributes (escape all user-controlled values)
        escaped_url = html_lib.escape(url or filename, quote=True)
        escaped_filename = html_lib.escape(filename or "")
        attrs = [f'href="{escaped_url}"']

        requires_python = pkg.get("requires_python")
        if requires_python:
            attrs.append(f'data-requires-python="{html_lib.escape(requires_python, quote=True)}"')

        pkg_hash = pkg.get("hash")
        if pkg_hash and "#" not in (url or "") and rename_rule is None and not strip_hashes:
            # Append hash as fragment (skip for renamed/patched packages — content changes)
            attrs[0] = f'href="{escaped_url}#{html_lib.escape(pkg_hash, quote=True)}"'

        link = f"    <a {' '.join(attrs)}>{escaped_filename}</a>"
        links.append(link)

    links_html = "\n".join(links)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Links for {html_lib.escape(project)}</title>
</head>
<body>
    <h1>Links for {html_lib.escape(project)}</h1>
{links_html}
</body>
</html>
"""
