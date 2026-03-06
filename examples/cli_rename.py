# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "urllib3>=2",
#   "urllib3_v1",
# ]
# ///

"""
Test CLI-based renaming with third-wheel run.

This script has no rename annotations in the metadata — the rename
is specified entirely on the command line.

Run with:

    third-wheel run examples/cli_rename.py --rename "urllib3<2=urllib3_v1"

This will:
  1. Download urllib3<2 from PyPI and rename it to urllib3_v1
  2. Install urllib3>=2 normally from PyPI
  3. Run the script with both available
"""

import urllib3
import urllib3_v1

print(f"urllib3 (v2): {urllib3.__version__}")
print(f"urllib3_v1:   {urllib3_v1.__version__}")

v2_major = int(urllib3.__version__.split(".")[0])
v1_major = int(urllib3_v1.__version__.split(".")[0])

assert v2_major >= 2, f"Expected urllib3 >= 2.x, got {urllib3.__version__}"
assert v1_major < 2, f"Expected urllib3_v1 < 2.x, got {urllib3_v1.__version__}"

print("Both versions installed and importable!")
