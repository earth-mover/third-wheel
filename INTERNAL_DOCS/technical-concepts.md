# Technical Concepts

## Wheel File Format (PEP 427)

- Wheels are ZIP files with `.whl` extension
- Structure: `{package}/`, `{package}-{version}.dist-info/`
- METADATA file contains package name, version, dependencies
- RECORD file contains SHA256 hashes of all files
- WHEEL file contains wheel metadata (generator, tags)

## Compiled Extensions Challenge

- `.so`/`.pyd` files contain `PyInit_{name}` symbol baked into binary
- This symbol MUST match the filename for Python to load the extension
- **Workaround**: If extension uses underscore prefix (e.g., `_icechunk_python.cpython-*.so`), parent directory can be renamed while keeping the `.so` filename unchanged
- Python imports `icechunk_v1._icechunk_python` and finds `PyInit__icechunk_python` correctly

## PEP 503 Simple Repository API

- Package indexes use this standard (PyPI, Anaconda.org)
- Root endpoint `/simple/` lists all projects
- Project endpoint `/simple/{project}/` lists all wheels
- Supports JSON variant (PEP 691) but HTML is most common

## Import Rewriting

The regex patterns in `_update_python_imports()` handle:

- `from pkg import x`
- `from pkg.submodule import x`
- `import pkg`
- `import pkg as alias`

Be careful with word boundaries (`\b`) to avoid partial matches.
