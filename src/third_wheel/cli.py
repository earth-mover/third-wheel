"""Command-line interface for third-wheel."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from third_wheel.download import download_compatible_wheel, list_wheels
from third_wheel.patch import patch_wheel
from third_wheel.rename import inspect_wheel, rename_wheel
from third_wheel.run import RenameSpec, parse_cli_renames, run_script

console = Console()
err_console = Console(stderr=True)


@click.group()
@click.version_option()
def main() -> None:
    """🛞 Third Wheel - Rename Python wheel packages for multi-version installation."""
    pass


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.argument("new_name")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output directory for the renamed wheel (default: same as input)",
)
@click.option(
    "--no-update-imports",
    is_flag=True,
    default=False,
    help="Do not update import statements in Python files",
)
def rename(
    wheel_path: Path,
    new_name: str,
    output: Path | None,
    no_update_imports: bool,
) -> None:
    """🛞 Rename a wheel package.

    WHEEL_PATH: Path to the wheel file to rename
    NEW_NAME: New package name (e.g., "icechunk_v1")
    """
    try:
        with console.status(f"[bold blue]Renaming {wheel_path.name}..."):
            result = rename_wheel(
                wheel_path,
                new_name,
                output_dir=output,
                update_imports=not no_update_imports,
            )

        console.print(f"[green]🛞 Created:[/green] [bold]{result}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.argument("old_dep")
@click.argument("new_dep")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output directory for the patched wheel (default: same as input)",
)
def patch(
    wheel_path: Path,
    old_dep: str,
    new_dep: str,
    output: Path | None,
) -> None:
    """🛞 Patch dependency references in a wheel.

    Rewrites all references to OLD_DEP → NEW_DEP inside the wheel's Python files
    without renaming the package itself. Useful after renaming a dependency with
    third-wheel rename.

    \b
    WHEEL_PATH: Path to the wheel file to patch
    OLD_DEP: Dependency name to replace (e.g., "zarr")
    NEW_DEP: Replacement dependency name (e.g., "zarr_v2")

    \b
    Example:
        third-wheel patch anemoi_datasets-0.5.31-py3-none-any.whl zarr zarr_v2 -o ./wheels/
    """
    try:
        with console.status(f"[bold blue]Patching {wheel_path.name}..."):
            result_path, patched_files = patch_wheel(
                wheel_path,
                old_dep,
                new_dep,
                output_dir=output,
            )

        if patched_files:
            console.print(f"[green]🛞 Patched {len(patched_files)} files:[/green]")
            for f in patched_files:
                console.print(f"  [dim]•[/dim] {f}")
        else:
            console.print("[yellow]🔧 No files needed patching[/yellow]")

        console.print(f"[green]🛞 Output:[/green] [bold]{result_path}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inspect(wheel_path: Path, as_json: bool) -> None:
    """🔧 Inspect a wheel's structure.

    WHEEL_PATH: Path to the wheel file to inspect
    """
    try:
        info = inspect_wheel(wheel_path)

        if as_json:
            click.echo(json.dumps(info, indent=2))
        else:
            # Create info table
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("Key", style="dim")
            table.add_column("Value", style="bold")

            table.add_row("Wheel", str(info["filename"]))
            table.add_row("Distribution", str(info["distribution"]))
            table.add_row("Version", str(info["version"]))
            table.add_row("Python", str(info["python_tag"]))
            table.add_row("ABI", str(info["abi_tag"]))
            table.add_row("Platform", str(info["platform_tag"]))

            console.print(Panel(table, title="[bold]🛞 Wheel Info[/bold]", border_style="blue"))

            extensions = info.get("extensions", [])
            if extensions:
                assert isinstance(extensions, list)

                ext_table = Table(show_header=True, header_style="bold")
                ext_table.add_column("Extension", style="cyan")
                ext_table.add_column("Renamable", justify="center")

                for ext in extensions:
                    assert isinstance(ext, dict)
                    if ext.get("has_underscore_prefix") == "True":
                        status = "[green]✓ Yes[/green]"
                    else:
                        status = "[red]✗ No[/red]"
                    ext_table.add_row(ext["path"], status)

                console.print(ext_table)
                console.print()

                if info.get("has_underscore_prefix_extension"):
                    console.print(
                        Panel(
                            "[green]This wheel uses underscore-prefix extensions.\n"
                            "Renaming should work correctly.[/green]",
                            title="[bold green]🛞 Safe to Rename[/bold green]",
                            border_style="green",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            "[yellow]This wheel has extensions without underscore prefix.\n"
                            "Renaming may cause import errors.\n"
                            "Consider rebuilding from source instead.[/yellow]",
                            title="[bold yellow]🔧 Warning[/bold yellow]",
                            border_style="yellow",
                        )
                    )
            else:
                console.print(
                    Panel(
                        "[green]No compiled extensions found (pure Python wheel).\n"
                        "Renaming should work correctly.[/green]",
                        title="[bold green]🛞 Safe to Rename[/bold green]",
                        border_style="green",
                    )
                )

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("package")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=Path(),
    help="Output directory for the downloaded wheel (default: current directory)",
)
@click.option(
    "-i",
    "--index-url",
    default="https://pypi.org/simple/",
    help="Base URL of the package index (default: PyPI)",
)
@click.option(
    "--version",
    "pkg_version",
    default=None,
    help="PEP 440 version specifier (e.g., '==1.0.0', '<2', '>=1.0,<2')",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List available wheels without downloading",
)
@click.option(
    "--rename",
    "rename_to",
    default=None,
    help="Rename the downloaded wheel to this package name",
)
@click.option(
    "--python-version",
    "python_version",
    default=None,
    help="Target Python version (e.g., '3.12'). Defaults to current interpreter.",
)
def download(
    package: str,
    output: Path,
    index_url: str,
    pkg_version: str | None,
    list_only: bool,
    rename_to: str | None,
    python_version: str | None,
) -> None:
    """🛞 Download a compatible wheel from a package index.

    PACKAGE: Name of the package to download

    Examples:

        third-wheel download numpy -o ./wheels/

        third-wheel download icechunk -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

        third-wheel download requests --list

        third-wheel download icechunk --version "<2" --rename icechunk_v1 -o ./wheels/

        third-wheel download icechunk --python-version 3.12 -o ./wheels/
    """
    try:
        if list_only:
            from packaging.version import Version

            with console.status(f"[bold blue]Fetching wheel list for {package}..."):
                wheels = list_wheels(package, index_url)

            if not wheels:
                err_console.print(f"[red]🔧[/red] No wheels found for [bold]{package}[/bold]")
                sys.exit(1)

            table = Table(title=f"Available wheels for [bold]{package}[/bold]")
            table.add_column("Filename", style="cyan")
            table.add_column("Version", style="green")

            for wheel in sorted(
                wheels,
                key=lambda w: Version(w.version) if w.version else Version("0"),
                reverse=True,
            ):
                table.add_row(wheel.filename, wheel.version or "unknown")

            console.print(table)
        else:
            with console.status(f"[bold blue]Finding compatible wheel for {package}..."):
                result = download_compatible_wheel(
                    package,
                    output,
                    index_url=index_url,
                    version=pkg_version,
                    python_version=python_version,
                    show_progress=False,  # We use rich status instead
                )

            if result is None:
                err_console.print(
                    f"[red]🔧[/red] No compatible wheel found for [bold]{package}[/bold]"
                )
                sys.exit(1)

            console.print(f"[green]🛞 Downloaded:[/green] [bold]{result}[/bold]")

            # Optionally rename the wheel
            if rename_to:
                with console.status(f"[bold blue]Renaming to {rename_to}..."):
                    renamed = rename_wheel(result, rename_to, output_dir=output)
                # Remove the original downloaded wheel
                result.unlink()
                console.print(f"[green]🛞 Renamed:[/green] [bold]{renamed}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to TOML config file",
)
@click.option(
    "-u",
    "--upstream",
    multiple=True,
    help="Upstream index URL (can be specified multiple times)",
)
@click.option(
    "-r",
    "--rename",
    "renames",
    multiple=True,
    help="Rename rule: 'original=new_name[:version_spec]' (can be specified multiple times)",
)
@click.option(
    "--host",
    default=None,
    help="Host to bind to (default: 127.0.0.1)",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="Port to listen on (default: 8000)",
)
def serve(
    config: Path | None,
    upstream: tuple[str, ...],
    renames: tuple[str, ...],
    host: str | None,
    port: int | None,
) -> None:
    """🛞 Start a PEP 503 proxy server with package renaming.

    The proxy server acts as a package index that can rename packages on-the-fly.
    This allows installing renamed packages via pip/uv.

    \b
    Examples:
        # Start with CLI options
        third-wheel serve \\
            -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \\
            -r "icechunk=icechunk_v1:<2"

        # Start with config file
        third-wheel serve -c proxy.toml

    \b
    Config file format (proxy.toml):
        [proxy]
        host = "127.0.0.1"
        port = 8000

        [[proxy.upstreams]]
        url = "https://pypi.org/simple/"

        [renames]
        icechunk = { name = "icechunk_v1", version = "<2" }
    """
    try:
        import uvicorn

        from third_wheel.server import create_app, load_config
    except ImportError as e:
        err_console.print(
            "[red]🔧 Error:[/red] Server dependencies not installed.\n"
            "Install with: [bold]pip install third-wheel[server][/bold]"
        )
        err_console.print(f"[dim]Missing: {e}[/dim]")
        sys.exit(1)

    try:
        # Load configuration
        cfg = load_config(
            config_path=config,
            upstreams=upstream if upstream else None,
            renames=renames if renames else None,
            host=host,
            port=port,
        )

        if not cfg.upstreams:
            err_console.print(
                "[red]🔧 Error:[/red] No upstream indexes configured.\n"
                "Use [bold]-u/--upstream[/bold] or config file."
            )
            sys.exit(1)

        if not cfg.renames and not cfg.patches:
            console.print(
                "[yellow]🔧 Warning:[/yellow] No rename or patch rules configured.\n"
                "The proxy will only serve virtual packages from rename/patch rules."
            )

        # Print startup info
        console.print(
            Panel.fit(
                f"[bold]🛞 third-wheel proxy[/bold]\n"
                f"Listening on: [cyan]http://{cfg.host}:{cfg.port}[/cyan]\n"
                f"Upstreams: {len(cfg.upstreams)}\n"
                f"Renames: {len(cfg.renames)}\n"
                f"Patches: {len(cfg.patches)}",
                border_style="blue",
            )
        )

        for rule in cfg.renames:
            version_info = f" ({rule.version_spec})" if rule.version_spec else ""
            console.print(
                f"  [dim]•[/dim] {rule.original} → [bold]{rule.new_name}[/bold]{version_info}"
            )

        for rule in cfg.patches:
            console.print(
                f"  [dim]•[/dim] {rule.package}: {rule.old_dep} → [bold]{rule.new_dep}[/bold]"
            )

        console.print()

        # Create and run the app
        app = create_app(cfg)
        uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--rename",
    "renames",
    multiple=True,
    help=(
        "Rename rule: 'original[version_spec]=new_name' "
        "(e.g., 'icechunk<2=icechunk_v1'). Can be specified multiple times."
    ),
)
@click.option(
    "-i",
    "--index-url",
    default="https://pypi.org/simple/",
    help="Package index URL for renamed packages (default: PyPI)",
)
@click.option(
    "--python-version",
    "python_version",
    default=None,
    help="Target Python version (e.g., '3.12'). Defaults to current interpreter.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print extra diagnostic info",
)
@click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
def run(
    script: Path,
    renames: tuple[str, ...],
    index_url: str,
    python_version: str | None,
    verbose: bool,
    script_args: tuple[str, ...],
) -> None:
    """Run a PEP 723 inline script with multi-version package support.

    \b
    Runs a Python script that uses PEP 723 inline metadata, with support
    for installing multiple versions of the same package under different
    names. Renames are detected from the script metadata and the packages
    are downloaded, renamed, and made available before the script runs
    via `uv run`.

    \b
    RENAME ANNOTATIONS
    ==================
    Add a comment after a dependency to mark it as a rename:

    \b
        # /// script
        # dependencies = [
        #   "icechunk_v1",  # icechunk<2
        #   "icechunk>=2",
        # ]
        # ///

    \b
    The comment syntax is:  "NEW_NAME",  # ORIGINAL_PKG VERSION_SPEC
    This tells third-wheel: install ORIGINAL_PKG (with VERSION_SPEC),
    but rename it to NEW_NAME so you can `import NEW_NAME`.

    \b
    For more complex setups, use the structured form:

    \b
        # /// script
        # dependencies = ["icechunk_v1", "icechunk>=2"]
        # [tool.third-wheel]
        # renames = [
        #   {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
        # ]
        # ///

    \b
    If both forms specify the same new-name, [tool.third-wheel] wins.

    \b
    CLI RENAMES
    ===========
    You can also specify renames on the command line with --rename.
    The format is:  ORIGINAL_PKG[VERSION_SPEC]=NEW_NAME

    \b
        third-wheel run script.py --rename "icechunk<2=icechunk_v1"

    \b
    CLI renames override any matching renames from the script metadata.

    \b
    ARGUMENT PASSING
    ================
    Unknown flags are passed through to the script automatically:

    \b
        third-wheel run script.py --my-flag value

    \b
    If the script uses a flag that conflicts with a third-wheel flag
    (e.g., --rename), use -- to separate them:

    \b
        third-wheel run script.py -- --rename "this-goes-to-script"

    \b
    EXAMPLES
    ========
        third-wheel run script.py
        third-wheel run script.py --rename "icechunk<2=icechunk_v1"
        third-wheel run script.py -i https://my-index/simple
        third-wheel run script.py -v --my-script-flag
        third-wheel run script.py -- --rename "arg-for-script"
    """
    try:
        cli_rename_specs = parse_cli_renames(renames) if renames else []

        exit_code = run_script(
            script_path=script,
            cli_renames=cli_rename_specs,
            index_url=index_url,
            python_version=python_version,
            script_args=list(script_args),
            verbose=verbose,
        )

        sys.exit(exit_code)

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command(name="sync")
@click.option(
    "--rename",
    "renames",
    multiple=True,
    help=(
        "Rename rule: 'original[version_spec]=new_name' "
        "(e.g., 'icechunk<2=icechunk_v1'). Can be specified multiple times. "
        "These are temporary (not saved to pyproject.toml)."
    ),
)
@click.option(
    "-i",
    "--index-url",
    default=None,
    help="Package index URL (default: PyPI, or index-url from [tool.third-wheel])",
)
@click.option(
    "--find-links",
    "find_links",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Local directory containing pre-built wheels (skips downloading from index)",
)
@click.option(
    "--python-version",
    "python_version",
    default=None,
    help="Target Python version (e.g., '3.12'). Defaults to current interpreter.",
)
@click.option(
    "-p",
    "--pyproject",
    "pyproject_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to pyproject.toml (default: auto-detect in current or parent dirs)",
)
@click.option(
    "--installer",
    type=click.Choice(["uv", "pip", "auto"]),
    default="auto",
    help="Installer to use: 'uv' (uv pip install), 'pip' (pip install), "
    "or 'auto' (detect — uses uv pip install --python targeting pixi/conda "
    "envs when CONDA_PREFIX is set, plain uv pip install otherwise)",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-download and re-rename wheels even if cached",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print extra diagnostic info",
)
def sync_cmd(
    renames: tuple[str, ...],
    index_url: str | None,
    find_links: Path | None,
    python_version: str | None,
    pyproject_path: Path | None,
    installer: str,
    force: bool,
    verbose: bool,
) -> None:
    """Install renamed packages into the current virtual environment.

    \b
    Reads rename specifications from pyproject.toml and/or CLI --rename flags,
    then downloads, renames, and installs the wheels via uv pip install
    (auto-detects pixi/conda environments via CONDA_PREFIX).

    \b
    PYPROJECT.TOML RENAMES
    ======================
    Declare renames in pyproject.toml's [tool.third-wheel] section:

    \b
        [tool.third-wheel]
        renames = [
            {original = "icechunk", new-name = "icechunk_v1", version = "<2"},
        ]

    \b
    Note: Do NOT add renamed packages to [project].dependencies or
    [dependency-groups] — uv sync would fail trying to resolve them.
    Use [tool.third-wheel] which uv ignores, and run third-wheel sync
    to install them separately.

    \b
    CLI RENAMES (TEMPORARY)
    =======================
    For one-off installs without modifying pyproject.toml:

    \b
        third-wheel sync --rename "icechunk<2=icechunk_v1"

    \b
    LOCAL WHEELS
    ============
    Use --find-links to source wheels from a local directory instead
    of downloading from a package index:

    \b
        third-wheel sync --find-links ./dist/ --rename "icechunk<2=icechunk_v1"

    \b
    EXAMPLES
    ========
        # Sync from pyproject.toml
        third-wheel sync

    \b
        # Temporary CLI-only rename
        third-wheel sync --rename "icechunk<2=icechunk_v1"

    \b
        # Use local wheels
        third-wheel sync --find-links ./dist/ --rename "mypkg<2=mypkg_v1"

    \b
        # Custom index
        third-wheel sync -i https://pypi.anaconda.org/.../simple
    """
    from third_wheel.sync import (
        get_pyproject_config,
        parse_renames_from_pyproject,
        sync,
    )

    try:
        # Parse CLI renames
        cli_rename_specs = parse_cli_renames(renames) if renames else []

        # Find and parse pyproject.toml
        pyproject_renames: list[RenameSpec] = []
        pyproject_config: dict[str, str] = {}

        explicitly_provided = pyproject_path is not None
        if pyproject_path is None:
            # Auto-detect: look in current dir and parents
            for candidate in [Path("pyproject.toml"), Path("../pyproject.toml")]:
                if candidate.exists():
                    pyproject_path = candidate
                    break

        if pyproject_path and not pyproject_path.exists():
            if explicitly_provided:
                err_console.print(f"[red]🔧 Error:[/red] {pyproject_path} not found.")
                sys.exit(1)
            pyproject_path = None

        if pyproject_path and pyproject_path.exists():
            pyproject_renames = parse_renames_from_pyproject(pyproject_path)
            pyproject_config = get_pyproject_config(pyproject_path)
            if verbose:
                err_console.print(
                    f"[dim]Read {len(pyproject_renames)} rename(s) from {pyproject_path}[/dim]"
                )

        # Merge: CLI renames override pyproject.toml renames
        from third_wheel.run import merge_renames

        all_renames = merge_renames(pyproject_renames, cli_rename_specs)

        if not all_renames:
            console.print(
                "[yellow]No renames found.[/yellow] Add renames to pyproject.toml or use --rename."
            )
            return

        # Resolve index URL: CLI > pyproject.toml config > default
        resolved_index = index_url or pyproject_config.get("index_url", "https://pypi.org/simple/")

        # Show what we're doing
        cli_new_names = {r.new_name for r in cli_rename_specs}
        for spec in all_renames:
            ver = f" ({spec.version})" if spec.version else ""
            source = "CLI" if spec.new_name in cli_new_names else "pyproject.toml"
            console.print(
                f"  [dim]{source}:[/dim] {spec.original}{ver} -> [bold]{spec.new_name}[/bold]"
            )

        # Run sync
        resolved_installer = installer if installer != "auto" else None
        with console.status("[bold blue]Syncing renamed packages..."):
            installed = sync(
                all_renames,
                index_url=resolved_index,
                find_links=find_links,
                python_version=python_version,
                installer=resolved_installer,
                force=force,
                verbose=verbose,
            )

        for wheel in installed:
            console.print(f"[green]Installed:[/green] [bold]{wheel.name}[/bold]")

        console.print(f"[green]Synced {len(installed)} renamed package(s).[/green]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command(name="add")
@click.argument("rename_spec")
@click.option(
    "--script",
    "script_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Add the rename to a PEP 723 inline script instead of pyproject.toml",
)
@click.option(
    "-i",
    "--index-url",
    default=None,
    help="Package index URL to store in config (saved to [tool.third-wheel])",
)
@click.option(
    "-p",
    "--pyproject",
    "pyproject_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to pyproject.toml (default: ./pyproject.toml)",
)
@click.option(
    "--sync/--no-sync",
    "run_sync",
    default=False,
    help="Also run 'third-wheel sync' after adding (default: no)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print extra diagnostic info",
)
def add_cmd(
    rename_spec: str,
    script_path: Path | None,
    index_url: str | None,
    pyproject_path: Path | None,
    run_sync: bool,
    verbose: bool,
) -> None:
    """Add a rename to pyproject.toml or a PEP 723 inline script.

    \b
    RENAME_SPEC format: 'original[version_spec]=new_name'

    \b
    EXAMPLES
    ========
        # Add to pyproject.toml
        third-wheel add "icechunk<2=icechunk_v1"

    \b
        # Add to a PEP 723 script
        third-wheel add --script myscript.py "icechunk<2=icechunk_v1"

    \b
        # Add and immediately install
        third-wheel add "icechunk<2=icechunk_v1" --sync

    \b
        # With a specific index
        third-wheel add "icechunk<2=icechunk_v1" -i https://pypi.anaconda.org/.../simple
    """
    from third_wheel.sync import (
        add_rename_to_pyproject,
        add_rename_to_script,
        get_pyproject_config,
        sync,
    )

    try:
        # Parse the rename spec
        specs = parse_cli_renames([rename_spec])
        if not specs:
            err_console.print("[red]🔧 Error:[/red] Could not parse rename spec.")
            sys.exit(1)
        spec = specs[0]

        if script_path is not None:
            # --- Script mode ---
            add_rename_to_script(script_path, spec)

            ver = f" ({spec.version})" if spec.version else ""
            console.print(
                f"[green]Added:[/green] {spec.original}{ver} "
                f"-> [bold]{spec.new_name}[/bold] to {script_path}"
            )
            return

        # --- pyproject.toml mode ---
        if pyproject_path is None:
            pyproject_path = Path("pyproject.toml")

        if not pyproject_path.exists():
            err_console.print(
                f"[red]🔧 Error:[/red] {pyproject_path} not found. "
                "Run this from your project root or use -p."
            )
            sys.exit(1)

        # Add to pyproject.toml
        add_rename_to_pyproject(pyproject_path, spec)

        ver = f" ({spec.version})" if spec.version else ""
        console.print(
            f"[green]Added:[/green] {spec.original}{ver} "
            f"-> [bold]{spec.new_name}[/bold] to {pyproject_path}"
        )

        # Optionally sync
        if run_sync:
            pyproject_config = get_pyproject_config(pyproject_path)
            resolved_index = index_url or pyproject_config.get(
                "index_url", "https://pypi.org/simple/"
            )
            with console.status("[bold blue]Syncing renamed packages..."):
                installed = sync(
                    [spec],
                    index_url=resolved_index,
                    verbose=verbose,
                )
            for wheel in installed:
                console.print(f"[green]Installed:[/green] [bold]{wheel.name}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command(name="cache-clean")
@click.option(
    "--sync-only",
    is_flag=True,
    default=False,
    help="Only clean the sync cache (preserve run cache)",
)
@click.option(
    "--run-only",
    is_flag=True,
    default=False,
    help="Only clean the run cache (preserve sync cache)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print details about what was removed",
)
def cache_clean_cmd(
    sync_only: bool,
    run_only: bool,
    verbose: bool,
) -> None:
    """Remove cached renamed wheels.

    \b
    Clears the third-wheel cache at ~/.cache/third-wheel/ (or
    $THIRD_WHEEL_CACHE_DIR). Use --sync-only or --run-only to
    selectively clean one namespace.

    \b
    EXAMPLES
    ========
        third-wheel cache-clean
        third-wheel cache-clean --sync-only
        third-wheel cache-clean -v
    """
    import shutil

    from third_wheel.run import cache_dir

    if sync_only and run_only:
        err_console.print("[red]🔧 Error:[/red] Cannot use both --sync-only and --run-only")
        sys.exit(1)

    root = cache_dir()
    if not root.exists():
        console.print("[dim]Cache directory does not exist — nothing to clean.[/dim]")
        return

    if sync_only:
        target = root / "sync"
        label = "sync"
    elif run_only:
        # The run cache is everything in root EXCEPT the sync/ subdir
        target = None
        label = "run"
    else:
        target = root
        label = "all"

    if target is not None:
        if not target.exists():
            console.print(f"[dim]No {label} cache to clean.[/dim]")
            return
        if verbose:
            # Count files
            wheel_count = len(list(target.rglob("*.whl")))
            console.print(f"[dim]Removing {wheel_count} cached wheel(s) from {target}[/dim]")
        shutil.rmtree(target)
        if target != root:
            # We only deleted a subdirectory; root still exists
            pass
    else:
        # run-only: remove everything except sync/
        removed = 0
        for child in root.iterdir():
            if child.name == "sync":
                continue
            if verbose:
                wheel_count = len(list(child.rglob("*.whl"))) if child.is_dir() else 0
                console.print(f"[dim]Removing {child.name} ({wheel_count} wheel(s))[/dim]")
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        if removed == 0:
            console.print("[dim]No run cache to clean.[/dim]")
            return

    console.print(f"[green]Cleaned {label} cache.[/green]")


if __name__ == "__main__":
    main()
