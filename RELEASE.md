# Release Process

third-wheel uses git tags for versioning ([hatch-vcs](https://github.com/ofek/hatch-vcs))
and publishes to PyPI via GitHub Releases with trusted publishing.

## Steps

1. **Ensure `main` is up to date and CI is green.**

2. **Create and push a git tag:**

   ```bash
   git checkout main
   git pull
   git tag v0.2.0       # or 0.2.0 — both formats work
   git push origin v0.2.0
   ```

3. **Create a GitHub Release:**

   ```bash
   gh release create v0.2.0 --generate-notes
   ```

   Or create it via the GitHub UI at
   <https://github.com/earth-mover/third-wheel/releases/new>.

4. **The publish workflow runs automatically** — it builds the package
   with `uv build` and publishes to PyPI via trusted publishing.

5. **Verify the release:**

   ```bash
   pip install third-wheel==0.2.0
   # or
   uvx third-wheel@0.2.0 --help
   ```

## How versioning works

- Tagged commits (e.g., `v0.2.0`) produce clean versions: `0.2.0`
- Untagged commits produce dev versions: `0.2.1.dev3+gabcdef`
- Both `v`-prefixed and plain version tags are supported

## Prerequisites

- The `pypi` environment must be configured in repo settings
  (Settings > Environments > pypi)
- Trusted publishing must be set up on PyPI for the
  `earth-mover/third-wheel` repository
  (<https://docs.pypi.org/trusted-publishers/>)
