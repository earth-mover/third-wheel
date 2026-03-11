"""Property-based tests using Hypothesis.

Tests invariants, roundtrip properties, and crash resistance across
the core third-wheel modules.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from third_wheel.rename import (
    _build_wheel_filename,
    _update_metadata,
    _update_python_imports,
    compute_record_hash,
    normalize_name,
    parse_wheel_filename,
    rename_wheel_from_bytes,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

package_name = st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True)
raw_package_name = st.from_regex(r"[a-zA-Z][a-zA-Z0-9._-]{0,20}", fullmatch=True)
version_str = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)


@st.composite
def wheel_components(draw: st.DrawFn) -> dict[str, str]:
    """Generate valid wheel filename components."""
    dist = draw(package_name)
    version = draw(version_str)
    build = draw(st.sampled_from(["", "1", "2build1"]))
    python = draw(st.sampled_from(["py3", "cp311", "cp312"]))
    abi = draw(st.sampled_from(["none", "cp311", "cp312", "abi3"]))
    platform = draw(st.sampled_from(["any", "linux_x86_64", "macosx_10_9_x86_64", "win_amd64"]))
    return {
        "distribution": dist,
        "version": version,
        "build": build,
        "python": python,
        "abi": abi,
        "platform": platform,
    }


@st.composite
def minimal_wheel_bytes(draw: st.DrawFn) -> tuple[bytes, str, str]:
    """Generate minimal valid wheel bytes with a known name and version."""
    name = draw(st.from_regex(r"[a-z][a-z0-9_]{1,12}", fullmatch=True))
    version = draw(version_str)
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
    return buf.getvalue(), name, version


# ---------------------------------------------------------------------------
# rename.py — normalize_name
# ---------------------------------------------------------------------------


class TestNormalizeNameProperties:
    @given(name=raw_package_name)
    def test_idempotent(self, name: str) -> None:
        """Normalizing twice gives the same result as normalizing once."""
        assert normalize_name(normalize_name(name)) == normalize_name(name)

    @given(name=raw_package_name)
    def test_no_hyphens_or_dots(self, name: str) -> None:
        """Output contains only lowercase, digits, and underscores."""
        result = normalize_name(name)
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in result)

    @given(name=raw_package_name)
    def test_no_consecutive_underscores(self, name: str) -> None:
        """Runs of separators collapse to a single underscore."""
        assert "__" not in normalize_name(name)


# ---------------------------------------------------------------------------
# rename.py — parse/build filename roundtrip
# ---------------------------------------------------------------------------


class TestFilenameRoundtripProperties:
    @given(components=wheel_components())
    def test_roundtrip(self, components: dict[str, str]) -> None:
        """Building then parsing a filename gives back the same components."""
        filename = _build_wheel_filename(components)
        parsed = parse_wheel_filename(filename)
        assert parsed == components

    @given(components=wheel_components())
    def test_always_has_required_keys(self, components: dict[str, str]) -> None:
        """Parsed filenames always contain all 6 required keys."""
        filename = _build_wheel_filename(components)
        parsed = parse_wheel_filename(filename)
        assert set(parsed.keys()) == {
            "distribution",
            "version",
            "build",
            "python",
            "abi",
            "platform",
        }


# ---------------------------------------------------------------------------
# rename.py — _update_python_imports
# ---------------------------------------------------------------------------


class TestImportRewritingProperties:
    @given(
        old_name=package_name,
        new_name=package_name,
        text=st.text(min_size=0, max_size=200),
    )
    def test_preserves_non_matching_lines(self, old_name: str, new_name: str, text: str) -> None:
        """Lines not containing old_name are unchanged."""
        # Filter to lines that don't contain the old name at all
        lines = [line for line in text.splitlines() if old_name not in line]
        if not lines:
            return
        content = "\n".join(lines).encode("utf-8")
        result = _update_python_imports(content, old_name, new_name)
        assert result == content

    @given(old_name=package_name, new_name=package_name)
    def test_binary_passthrough(self, old_name: str, new_name: str) -> None:
        """Non-UTF8 bytes are returned unchanged."""
        content = b"\x80\x81\x82\xff"
        result = _update_python_imports(content, old_name, new_name)
        assert result == content

    @given(
        name=package_name,
        text=st.from_regex(r"(from [a-z]+ import \w+\n?){1,5}", fullmatch=True),
    )
    def test_idempotent(self, name: str, text: str) -> None:
        """Renaming with same old and new name is identity."""
        content = text.encode("utf-8")
        result = _update_python_imports(content, name, name)
        assert result == content


# ---------------------------------------------------------------------------
# rename.py — rename_wheel_from_bytes
# ---------------------------------------------------------------------------


class TestRenameWheelRoundtripProperties:
    @given(data=minimal_wheel_bytes())
    @settings(max_examples=50, deadline=5000)
    def test_preserves_file_count(self, data: tuple[bytes, str, str]) -> None:
        """Renaming doesn't change the number of files in the wheel."""
        wheel_bytes, name, _version = data
        new_name = name + "_v1"
        renamed = rename_wheel_from_bytes(wheel_bytes, new_name)

        with zipfile.ZipFile(BytesIO(wheel_bytes)) as orig_zf:
            orig_count = len(orig_zf.namelist())
        with zipfile.ZipFile(BytesIO(renamed)) as new_zf:
            new_count = len(new_zf.namelist())

        assert orig_count == new_count

    @given(data=minimal_wheel_bytes())
    @settings(max_examples=50, deadline=5000)
    def test_roundtrip(self, data: tuple[bytes, str, str]) -> None:
        """Renaming A->B then B->A restores the original file list and .py content."""
        wheel_bytes, name, _version = data
        new_name = name + "_v1"

        renamed = rename_wheel_from_bytes(wheel_bytes, new_name)
        restored = rename_wheel_from_bytes(renamed, name)

        with zipfile.ZipFile(BytesIO(wheel_bytes)) as orig_zf:
            orig_files = sorted(orig_zf.namelist())
            orig_py = {n: orig_zf.read(n) for n in orig_files if n.endswith(".py")}
        with zipfile.ZipFile(BytesIO(restored)) as rest_zf:
            rest_files = sorted(rest_zf.namelist())
            rest_py = {n: rest_zf.read(n) for n in rest_files if n.endswith(".py")}

        assert orig_files == rest_files
        assert orig_py == rest_py


# ---------------------------------------------------------------------------
# run.py — parse_pep723_metadata
# ---------------------------------------------------------------------------


class TestPEP723Properties:
    @given(script=st.text(min_size=0, max_size=500))
    def test_never_crashes(self, script: str) -> None:
        """Arbitrary strings never cause a crash."""
        from third_wheel.run import parse_pep723_metadata

        result = parse_pep723_metadata(script)
        assert result is None or isinstance(result, str)

    @given(
        toml_lines=st.lists(
            st.from_regex(r"[a-z]+ = \"[a-z0-9]+\"", fullmatch=True),
            min_size=1,
            max_size=3,
        ),
    )
    def test_roundtrip(self, toml_lines: list[str]) -> None:
        """Embedded TOML in a valid script block is extracted correctly."""
        from third_wheel.run import parse_pep723_metadata

        block = "\n".join(["# /// script"] + [f"# {line}" for line in toml_lines] + ["# ///"])
        script = f"# preamble\n{block}\nprint('hello')\n"
        result = parse_pep723_metadata(script)
        assert result == "\n".join(toml_lines)


# ---------------------------------------------------------------------------
# run.py — parse_cli_renames
# ---------------------------------------------------------------------------


class TestCLIRenameProperties:
    @given(
        original=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True),
        version=st.one_of(st.just(""), st.from_regex(r"<[0-9]+", fullmatch=True)),
        new_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True),
    )
    def test_roundtrip(self, original: str, version: str, new_name: str) -> None:
        """Valid CLI args parse to correct RenameSpec fields."""
        from third_wheel.run import parse_cli_renames

        arg = f"{original}{version}={new_name}"
        result = parse_cli_renames([arg])
        assert len(result) == 1
        assert result[0].original == original
        assert result[0].new_name == new_name
        if version:
            assert result[0].version == version

    @given(arg=st.text(min_size=1, max_size=50).filter(lambda s: "=" not in s))
    def test_rejects_no_equals(self, arg: str) -> None:
        """Strings without '=' raise ValueError."""
        from third_wheel.run import parse_cli_renames

        with pytest.raises(ValueError, match="Invalid --rename format"):
            parse_cli_renames([arg])


# ---------------------------------------------------------------------------
# patch.py — _update_dependency_references
# ---------------------------------------------------------------------------


class TestPatchReferencesProperties:
    @given(old_name=package_name, new_name=package_name)
    def test_preserves_dotted_extensions(self, old_name: str, new_name: str) -> None:
        """Dotted references like '.zarr' are not rewritten."""
        from third_wheel.patch import _update_dependency_references

        content = f"path = 'file.{old_name}'".encode()
        result = _update_dependency_references(content, old_name, new_name)
        assert f"file.{old_name}".encode() in result

    @given(old_name=package_name, new_name=package_name)
    def test_binary_passthrough(self, old_name: str, new_name: str) -> None:
        """Non-UTF8 bytes are returned unchanged."""
        from third_wheel.patch import _update_dependency_references

        content = b"\x80\x81\x82\xff"
        result = _update_dependency_references(content, old_name, new_name)
        assert result == content


# ---------------------------------------------------------------------------
# server/html.py — generate_project_index
# ---------------------------------------------------------------------------


class TestHTMLGenerationProperties:
    @given(
        project=st.text(min_size=1, max_size=50),
        filename=st.text(min_size=1, max_size=50),
    )
    @settings(deadline=None)
    def test_no_unescaped_specials(self, project: str, filename: str) -> None:
        """User-controlled values with HTML special chars are escaped."""
        from third_wheel.server.html import generate_project_index

        packages = [{"filename": filename, "url": None, "requires_python": None, "hash": None}]
        html = generate_project_index(project, packages)  # type: ignore[arg-type]
        # Raw < and > from user input must not appear unescaped
        # (they should be &lt; and &gt;)
        if "<" in project:
            assert f"<h1>Links for {project}</h1>" not in html
        if ">" in project:
            assert f"<h1>Links for {project}</h1>" not in html

    @given(
        project=st.text(min_size=1, max_size=30),
        filenames=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
    )
    def test_never_crashes(self, project: str, filenames: list[str]) -> None:
        """Arbitrary project names and filenames don't crash."""
        from third_wheel.server.html import generate_project_index

        packages = [
            {"filename": f, "url": None, "requires_python": None, "hash": None} for f in filenames
        ]
        result = generate_project_index(project, packages)  # type: ignore[arg-type]
        assert "<!DOCTYPE html>" in result


# ---------------------------------------------------------------------------
# rename.py — compute_record_hash
# ---------------------------------------------------------------------------


class TestComputeRecordHashProperties:
    @given(data=st.binary(min_size=0, max_size=1000))
    def test_format(self, data: bytes) -> None:
        """Output always matches sha256=<base64url> format."""
        result = compute_record_hash(data)
        assert result.startswith("sha256=")
        # Base64 urlsafe chars: A-Z, a-z, 0-9, -, _
        payload = result[len("sha256=") :]
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in payload
        )

    @given(data=st.binary(min_size=0, max_size=1000))
    def test_deterministic(self, data: bytes) -> None:
        """Same bytes always produce the same hash."""
        assert compute_record_hash(data) == compute_record_hash(data)

    @given(a=st.binary(min_size=1, max_size=100), b=st.binary(min_size=1, max_size=100))
    def test_different_inputs_different_hashes(self, a: bytes, b: bytes) -> None:
        """Different inputs produce different hashes (with overwhelming probability)."""
        if a != b:
            assert compute_record_hash(a) != compute_record_hash(b)


# ---------------------------------------------------------------------------
# rename.py — _update_metadata
# ---------------------------------------------------------------------------


class TestUpdateMetadataProperties:
    @given(name=package_name, new_name=package_name, version=version_str)
    def test_updates_name_field(self, name: str, new_name: str, version: str) -> None:
        """The Name: field is updated to the new name."""
        content = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
        result = _update_metadata(content, name, new_name)
        text = result.decode("utf-8")
        assert f"Name: {new_name}" in text

    @given(name=package_name, new_name=package_name, version=version_str)
    def test_preserves_other_fields(self, name: str, new_name: str, version: str) -> None:
        """Non-Name lines are unchanged."""
        content = (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: test\n".encode()
        )
        result = _update_metadata(content, name, new_name)
        text = result.decode("utf-8")
        assert "Metadata-Version: 2.1" in text
        assert f"Version: {version}" in text
        assert "Summary: test" in text

    @given(name=package_name, version=version_str)
    def test_idempotent(self, name: str, version: str) -> None:
        """Updating with same name is identity."""
        content = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
        result = _update_metadata(content, name, name)
        assert result == content


# ---------------------------------------------------------------------------
# download.py — parse_wheel_tags
# ---------------------------------------------------------------------------


class TestParseWheelTagsProperties:
    @given(components=wheel_components())
    def test_valid_filename_returns_tags(self, components: dict[str, str]) -> None:
        """Valid wheel filenames produce at least one tag."""
        from third_wheel.download import parse_wheel_tags

        filename = _build_wheel_filename(components)
        tags = parse_wheel_tags(filename)
        assert len(tags) >= 1

    @given(components=wheel_components())
    def test_tag_components_match(self, components: dict[str, str]) -> None:
        """Tags contain the python/abi/platform from the filename."""
        from third_wheel.download import parse_wheel_tags

        filename = _build_wheel_filename(components)
        tags = parse_wheel_tags(filename)
        tag = tags[0]
        assert tag.interpreter == components["python"]
        assert tag.abi == components["abi"]
        assert tag.platform == components["platform"]

    @given(text=st.text(min_size=0, max_size=50))
    def test_never_crashes(self, text: str) -> None:
        """Arbitrary strings never crash (return empty list on invalid)."""
        from third_wheel.download import parse_wheel_tags

        result = parse_wheel_tags(text + ".whl")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# run.py — merge_renames
# ---------------------------------------------------------------------------


class TestMergeRenamesProperties:
    @given(
        names=st.lists(
            st.tuples(
                st.from_regex(r"[a-z]{2,8}", fullmatch=True),
                st.from_regex(r"[a-z]{2,8}_v[12]", fullmatch=True),
            ),
            min_size=0,
            max_size=5,
            unique_by=lambda x: x[1],
        ),
    )
    def test_cli_always_present(self, names: list[tuple[str, str]]) -> None:
        """All CLI renames appear in the merge result."""
        from third_wheel.run import RenameSpec, merge_renames

        cli = [RenameSpec(original=o, new_name=n) for o, n in names]
        result = merge_renames([], cli)
        result_new_names = {r.new_name for r in result}
        for r in cli:
            assert r.new_name in result_new_names

    @given(
        script_names=st.lists(
            st.tuples(
                st.from_regex(r"[a-z]{2,8}", fullmatch=True),
                st.from_regex(r"[a-z]{2,8}_v1", fullmatch=True),
            ),
            min_size=0,
            max_size=3,
            unique_by=lambda x: x[1],
        ),
        cli_names=st.lists(
            st.tuples(
                st.from_regex(r"[a-z]{2,8}", fullmatch=True),
                st.from_regex(r"[a-z]{2,8}_v2", fullmatch=True),
            ),
            min_size=0,
            max_size=3,
            unique_by=lambda x: x[1],
        ),
    )
    def test_no_duplicate_new_names(
        self, script_names: list[tuple[str, str]], cli_names: list[tuple[str, str]]
    ) -> None:
        """Result never contains duplicate new_names."""
        from third_wheel.run import RenameSpec, merge_renames

        script = [RenameSpec(original=o, new_name=n) for o, n in script_names]
        cli = [RenameSpec(original=o, new_name=n) for o, n in cli_names]
        result = merge_renames(script, cli)
        new_names = [r.new_name for r in result]
        assert len(new_names) == len(set(new_names))


# ---------------------------------------------------------------------------
# run.py — extract_renames_from_comments
# ---------------------------------------------------------------------------


class TestExtractRenamesFromCommentsProperties:
    @given(
        original=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,10}", fullmatch=True),
        version=st.one_of(st.just(""), st.from_regex(r"<[0-9]+\.[0-9]+", fullmatch=True)),
    )
    def test_roundtrip(self, original: str, new_name: str, version: str) -> None:
        """Comment-style annotations are correctly extracted."""
        from third_wheel.run import extract_renames_from_comments

        line = f'"{new_name}",  # {original}{version}'
        result = extract_renames_from_comments(line)
        assert len(result) == 1
        assert result[0].original == original
        assert result[0].new_name == new_name

    @given(text=st.text(min_size=0, max_size=200))
    def test_never_crashes(self, text: str) -> None:
        """Arbitrary text never crashes."""
        from third_wheel.run import extract_renames_from_comments

        result = extract_renames_from_comments(text)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# run.py — extract_renames_from_tool_table
# ---------------------------------------------------------------------------


class TestExtractRenamesFromToolTableProperties:
    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v[12]", fullmatch=True),
    )
    def test_roundtrip(self, original: str, new_name: str) -> None:
        """Valid TOML with [tool.third-wheel] renames is extracted correctly."""
        from third_wheel.run import extract_renames_from_tool_table

        toml_str = (
            f"[tool.third-wheel]\n"
            f"renames = [\n"
            f'  {{original = "{original}", new-name = "{new_name}"}},\n'
            f"]\n"
        )
        result = extract_renames_from_tool_table(toml_str)
        assert len(result) == 1
        assert result[0].original == original
        assert result[0].new_name == new_name

    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v[12]", fullmatch=True),
        source=st.from_regex(r"git\+https://[a-z]+\.[a-z]+/[a-z]+@[a-z]+", fullmatch=True),
    )
    def test_roundtrip_with_source(self, original: str, new_name: str, source: str) -> None:
        """Valid TOML with source field is extracted correctly."""
        from third_wheel.run import extract_renames_from_tool_table

        toml_str = (
            f"[tool.third-wheel]\n"
            f"renames = [\n"
            f'  {{original = "{original}", new-name = "{new_name}", source = "{source}"}},\n'
            f"]\n"
        )
        result = extract_renames_from_tool_table(toml_str)
        assert len(result) == 1
        assert result[0].original == original
        assert result[0].new_name == new_name
        assert result[0].source == source

    @given(text=st.text(min_size=0, max_size=300))
    def test_never_crashes(self, text: str) -> None:
        """Arbitrary text never crashes (returns empty list on invalid TOML)."""
        from third_wheel.run import extract_renames_from_tool_table

        result = extract_renames_from_tool_table(text)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# run.py — RenameSpec.version_spec
# ---------------------------------------------------------------------------


class TestRenameSpecProperties:
    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        version=st.from_regex(r"<[0-9]+\.[0-9]+", fullmatch=True),
    )
    def test_version_spec_with_version(self, original: str, version: str) -> None:
        """version_spec includes version when set."""
        from third_wheel.run import RenameSpec

        spec = RenameSpec(original=original, new_name="x", version=version)
        assert spec.version_spec == f"{original}{version}"

    @given(original=st.from_regex(r"[a-z]{2,10}", fullmatch=True))
    def test_version_spec_without_version(self, original: str) -> None:
        """version_spec is just original when no version."""
        from third_wheel.run import RenameSpec

        spec = RenameSpec(original=original, new_name="x")
        assert spec.version_spec == original

    def test_source_type_index_when_none(self) -> None:
        """source_type is 'index' when source is None."""
        from third_wheel.run import RenameSpec

        spec = RenameSpec(original="x", new_name="y")
        assert spec.source_type == "index"

    @given(
        url=st.from_regex(r"git\+https://[a-z]+\.[a-z]+/[a-z]+@[a-z]+", fullmatch=True),
    )
    def test_source_type_git(self, url: str) -> None:
        """source_type is 'git' for git+ URLs."""
        from third_wheel.run import RenameSpec

        spec = RenameSpec(original="x", new_name="y", source=url)
        assert spec.source_type == "git"

    @given(
        path=st.from_regex(r"/[a-z]+/[a-z]+", fullmatch=True),
    )
    def test_source_type_path(self, path: str) -> None:
        """source_type is 'path' for non-git sources."""
        from third_wheel.run import RenameSpec

        spec = RenameSpec(original="x", new_name="y", source=path)
        assert spec.source_type == "path"


# ---------------------------------------------------------------------------
# run.py — rename_cache_key
# ---------------------------------------------------------------------------


class TestRenameCacheKeyProperties:
    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
        index_url=st.from_regex(r"https://[a-z]+\.[a-z]+/simple/", fullmatch=True),
    )
    def test_deterministic(self, original: str, new_name: str, index_url: str) -> None:
        """Same inputs always produce the same cache key."""
        from third_wheel.run import RenameSpec, rename_cache_key

        renames = [RenameSpec(original=original, new_name=new_name)]
        key1 = rename_cache_key(renames, index_url, None)
        key2 = rename_cache_key(renames, index_url, None)
        assert key1 == key2

    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
    )
    def test_format(self, original: str, new_name: str) -> None:
        """Cache key is always a 16-char hex string."""
        from third_wheel.run import RenameSpec, rename_cache_key

        renames = [RenameSpec(original=original, new_name=new_name)]
        key = rename_cache_key(renames, "https://pypi.org/simple/", None)
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)

    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
    )
    def test_source_changes_key(self, original: str, new_name: str) -> None:
        """Different source values produce different cache keys."""
        from third_wheel.run import RenameSpec, rename_cache_key

        index_url = "https://pypi.org/simple/"
        key_no_source = rename_cache_key(
            [RenameSpec(original=original, new_name=new_name)], index_url, None
        )
        key_with_source = rename_cache_key(
            [
                RenameSpec(
                    original=original, new_name=new_name, source="git+https://example.com/repo@main"
                )
            ],
            index_url,
            None,
        )
        assert key_no_source != key_with_source


# ---------------------------------------------------------------------------
# server/config.py — parse_rename_arg
# ---------------------------------------------------------------------------


class TestServerParseRenameArgProperties:
    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
    )
    def test_roundtrip_basic(self, original: str, new_name: str) -> None:
        """'original=new_name' parses correctly."""
        from third_wheel.server.config import parse_rename_arg

        result = parse_rename_arg(f"{original}={new_name}")
        assert result.original == original
        assert result.new_name == new_name
        assert result.version_spec is None

    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
        version=st.from_regex(r"<[0-9]+\.[0-9]+", fullmatch=True),
    )
    def test_roundtrip_with_version(self, original: str, new_name: str, version: str) -> None:
        """'original=new_name:version' parses correctly."""
        from third_wheel.server.config import parse_rename_arg

        result = parse_rename_arg(f"{original}={new_name}:{version}")
        assert result.original == original
        assert result.new_name == new_name
        assert result.version_spec == version

    @given(arg=st.text(min_size=1, max_size=30).filter(lambda s: "=" not in s))
    def test_rejects_no_equals(self, arg: str) -> None:
        """Strings without '=' raise ValueError."""
        from third_wheel.server.config import parse_rename_arg

        with pytest.raises(ValueError, match="Invalid rename format"):
            parse_rename_arg(arg)


# ---------------------------------------------------------------------------
# server/config.py — _normalize_name (PEP 503 dash variant)
# ---------------------------------------------------------------------------


class TestServerNormalizeNameProperties:
    @given(name=raw_package_name)
    def test_idempotent(self, name: str) -> None:
        """Normalizing twice gives the same result."""
        from third_wheel.server.config import _normalize_name

        assert _normalize_name(_normalize_name(name)) == _normalize_name(name)

    @given(name=raw_package_name)
    def test_output_charset(self, name: str) -> None:
        """Output contains only lowercase, digits, and dashes."""
        from third_wheel.server.config import _normalize_name

        result = _normalize_name(name)
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in result)

    @given(name=raw_package_name)
    def test_no_consecutive_dashes(self, name: str) -> None:
        """Runs of separators collapse to a single dash."""
        from third_wheel.server.config import _normalize_name

        assert "--" not in _normalize_name(name)


# ---------------------------------------------------------------------------
# server/config.py — ProxyConfig lookup
# ---------------------------------------------------------------------------


class TestProxyConfigLookupProperties:
    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
    )
    def test_rename_rule_lookup(self, original: str, new_name: str) -> None:
        """get_rename_rule finds rules by normalized new_name."""
        from third_wheel.server.config import ProxyConfig, RenameRule

        config = ProxyConfig(renames=[RenameRule(original=original, new_name=new_name)])
        assert config.get_rename_rule(new_name) is not None
        assert config.is_renamed_package(new_name)
        assert config.get_original_for_renamed(new_name) == original

    @given(
        original=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
        new_name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True),
    )
    def test_rename_rule_normalized_lookup(self, original: str, new_name: str) -> None:
        """PEP 503 normalization: underscores match dashes in lookup."""
        from third_wheel.server.config import ProxyConfig, RenameRule

        config = ProxyConfig(renames=[RenameRule(original=original, new_name=new_name)])
        # Convert underscores to dashes — should still find the rule
        dashed = new_name.replace("_", "-")
        assert config.get_rename_rule(dashed) is not None

    @given(name=st.from_regex(r"[a-z]{2,10}_v1", fullmatch=True))
    def test_no_false_positive(self, name: str) -> None:
        """Empty config never matches."""
        from third_wheel.server.config import ProxyConfig

        config = ProxyConfig()
        assert config.get_rename_rule(name) is None
        assert not config.is_renamed_package(name)


# ---------------------------------------------------------------------------
# server/html.py — generate_root_index
# ---------------------------------------------------------------------------


class TestRootIndexProperties:
    @given(
        projects=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=10),
    )
    @settings(deadline=None)
    def test_never_crashes(self, projects: list[str]) -> None:
        """Arbitrary project names don't crash."""
        from third_wheel.server.html import generate_root_index

        result = generate_root_index(projects)
        assert "<!DOCTYPE html>" in result

    @given(
        projects=st.lists(
            st.from_regex(r"[a-z]{2,10}", fullmatch=True),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(deadline=None)
    def test_all_projects_present(self, projects: list[str]) -> None:
        """All project names appear in the output HTML."""
        from third_wheel.server.html import generate_root_index

        result = generate_root_index(projects)
        for p in projects:
            assert p in result

    @given(
        projects=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5),
    )
    @settings(deadline=None)
    def test_deduplicates(self, projects: list[str]) -> None:
        """Duplicate project names are deduplicated."""
        from third_wheel.server.html import generate_root_index

        doubled = projects + projects
        result = generate_root_index(doubled)
        # Count link occurrences — each unique project should appear once
        for p in set(projects):
            import html as html_lib

            escaped = html_lib.escape(p)
            count = result.count(f">{escaped}</a>")
            assert count == 1


# ---------------------------------------------------------------------------
# server/stream.py — rewrite_wheel_filename / original_filename_from_renamed
# ---------------------------------------------------------------------------


class TestFilenameRewriteProperties:
    @given(
        components=wheel_components(),
        new_name=package_name,
    )
    def test_roundtrip(self, components: dict[str, str], new_name: str) -> None:
        """rewrite then reverse gives back the normalized original filename."""
        from third_wheel.server.stream import original_filename_from_renamed, rewrite_wheel_filename

        # normalize_name collapses separators, so roundtrip only works with
        # already-normalized distribution names
        components = {**components, "distribution": normalize_name(components["distribution"])}
        original_name = components["distribution"]
        filename = _build_wheel_filename(components)

        rewritten = rewrite_wheel_filename(filename, original_name, new_name)
        restored = original_filename_from_renamed(rewritten, original_name, new_name)
        assert restored == filename

    @given(components=wheel_components())
    def test_preserves_version_and_tags(self, components: dict[str, str]) -> None:
        """Rewritten filename keeps version, python, abi, platform."""
        from third_wheel.server.stream import rewrite_wheel_filename

        filename = _build_wheel_filename(components)
        rewritten = rewrite_wheel_filename(filename, components["distribution"], "new_pkg")
        parsed = parse_wheel_filename(rewritten)
        assert parsed["version"] == components["version"]
        assert parsed["python"] == components["python"]
        assert parsed["abi"] == components["abi"]
        assert parsed["platform"] == components["platform"]


# ---------------------------------------------------------------------------
# patch.py — _update_dependency_references (additional properties)
# ---------------------------------------------------------------------------


class TestPatchReferencesAdditionalProperties:
    @given(name=package_name)
    def test_idempotent_same_name(self, name: str) -> None:
        """Patching with same old and new name is identity."""
        from third_wheel.patch import _update_dependency_references

        content = f"import {name}\nfrom {name} import foo\n".encode()
        result = _update_dependency_references(content, name, name)
        assert result == content

    @given(
        old_name=package_name,
        new_name=package_name,
        prefix=st.from_regex(r"[a-z]{1,5}", fullmatch=True),
    )
    def test_word_boundary(self, old_name: str, new_name: str, prefix: str) -> None:
        """Partial matches within longer words are not rewritten."""
        from third_wheel.patch import _update_dependency_references

        # e.g., "lazy_zarr" should not become "lazy_zarr_v2" when patching "zarr"
        compound = f"{prefix}{old_name}"
        content = f"import {compound}\n".encode()
        result = _update_dependency_references(content, old_name, new_name)
        # The compound name should still be present (not partially rewritten)
        assert compound.encode() in result
