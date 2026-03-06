# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "icechunk_v1",  # icechunk<2
#   "icechunk>=2.0.0a0",
#   "zarr>=3.0.0b0",
# ]
#
# [[tool.uv.index]]
# name = "scientific-python-nightly-wheels"
# url = "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple"
#
# [tool.uv]
# index-strategy = "unsafe-best-match"
#
# [tool.uv.sources]
# icechunk = { index = "scientific-python-nightly-wheels" }
# zarr = { index = "scientific-python-nightly-wheels" }
# ///

"""
Dual icechunk version example.

Run with:

    third-wheel run examples/icechunk_dual_version.py \
        -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

This will:
  1. Download icechunk<2 from the nightly index and rename it to icechunk_v1
  2. Install icechunk>=2.0.0a0 from the nightly index (via uv's [tool.uv.sources])
  3. Install zarr>=3 from the nightly index
  4. Everything else from PyPI
"""

import icechunk
import icechunk_v1

print(f"icechunk v1: {icechunk_v1.__version__}")
print(f"icechunk v2: {icechunk.__version__}")

# Sanity check that they're actually different major versions
v1_major = int(icechunk_v1.__version__.split(".")[0])
v2_major = int(icechunk.__version__.split(".")[0])

assert v1_major < 2, f"Expected icechunk_v1 to be 1.x, got {icechunk_v1.__version__}"
assert v2_major >= 2, f"Expected icechunk to be 2.x, got {icechunk.__version__}"

print("Both versions installed and importable!")
