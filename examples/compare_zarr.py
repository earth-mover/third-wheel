# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "zarr_v2",  # zarr>=2.18,<3
#   "zarr_dev",
#   "numpy",
# ]
# [tool.third-wheel]
# renames = [
#   {original = "zarr", new-name = "zarr_dev", source = "git+https://github.com/zarr-developers/zarr-python@main"},
# ]
# ///

"""
Can zarr v3 (from git main) still read your zarr v2 data? And can v2 users read v3 files?

This example uses two rename strategies:
- zarr_v2: released zarr v2 from PyPI (comment-style rename)
- zarr_dev: latest zarr from git main (structured rename with source)

Run with:  third-wheel run examples/compare_zarr.py
"""

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import zarr_dev
import zarr_v2

print(f"zarr v2 (PyPI): {zarr_v2.__version__}")
print(f"zarr dev (git): {zarr_dev.__version__}")

tmpdir = Path(tempfile.mkdtemp())
data = np.random.default_rng(42).random((500, 500))

# --- Cross-version compatibility ---
print("\n=== Can they read each other's files? ===")

# v2 writes → dev reads
path = str(tmpdir / "written_by_v2.zarr")
z = zarr_v2.open(path, mode="w", shape=data.shape, dtype=data.dtype)
z[:] = data
try:
    result = zarr_dev.open_array(path, mode="r")[:]
    print(f"v2 writes, dev reads: {'OK' if np.array_equal(data, result) else 'MISMATCH'}")
except Exception as e:
    print(f"v2 writes, dev reads: FAILED — {e}")

# dev writes (v3 format) → v2 reads
path = str(tmpdir / "written_by_dev.zarr")
z = zarr_dev.open_array(path, mode="w", shape=data.shape, dtype=data.dtype)
z[:] = data
try:
    result = zarr_v2.open(path, mode="r")[:]
    print(f"dev writes, v2 reads: {'OK' if np.array_equal(data, result) else 'MISMATCH'}")
except Exception as e:
    print(f"dev writes, v2 reads: FAILED — {e}")

# dev writes in v2-compatible format → v2 reads
path = str(tmpdir / "written_by_dev_compat.zarr")
z = zarr_dev.open_array(path, mode="w", shape=data.shape, dtype=data.dtype, zarr_format=2)
z[:] = data
try:
    result = zarr_v2.open(path, mode="r")[:]
    print(
        f"dev writes (format=2), v2 reads: {'OK' if np.array_equal(data, result) else 'MISMATCH'}"
    )
except Exception as e:
    print(f"dev writes (format=2), v2 reads: FAILED — {e}")

# --- Speed comparison ---
print("\n=== Write + read speed (500x500 float64) ===")

path = str(tmpdir / "bench_v2.zarr")
t0 = time.perf_counter()
z = zarr_v2.open(path, mode="w", shape=data.shape, dtype=data.dtype)
z[:] = data
_ = zarr_v2.open(path, mode="r")[:]
t_v2 = time.perf_counter() - t0

path = str(tmpdir / "bench_dev.zarr")
t0 = time.perf_counter()
z = zarr_dev.open_array(path, mode="w", shape=data.shape, dtype=data.dtype)
z[:] = data
_ = zarr_dev.open_array(path, mode="r")[:]
t_dev = time.perf_counter() - t0

print(f"v2: {t_v2:.3f}s   dev: {t_dev:.3f}s   ratio: {t_dev / t_v2:.1f}x")

shutil.rmtree(tmpdir)
