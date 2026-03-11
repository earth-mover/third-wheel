# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "skimage_old",  # scikit-image>=0.24,<0.25
#   "scikit-image>=0.26",
#   "numpy",
# ]
# ///

"""
Same image, same filter, same parameters — different pixels?

Catches silent numerical changes between scikit-image versions.

Run with:  third-wheel run examples/compare_skimage.py
"""

import numpy as np
import skimage.feature as feature_new
import skimage.filters as filters_new
import skimage_old.feature as feature_old
import skimage_old.filters as filters_old
from skimage.data import coins

img = coins().astype(float)
print(f"Test image: {img.shape}\n")


def compare(label, old, new):
    if np.array_equal(old, new):
        print(f"  EXACT    {label}")
    elif np.allclose(old, new):
        print(f"  ~EQUAL   {label} (within tolerance)")
    else:
        diff = np.abs(old.astype(float) - new.astype(float))
        changed = np.count_nonzero(diff)
        print(f"  DIFFERS  {label}: {changed} pixels changed, max diff={diff.max():.4g}")


compare("gaussian(sigma=2)", filters_old.gaussian(img, sigma=2), filters_new.gaussian(img, sigma=2))
compare("sobel", filters_old.sobel(img), filters_new.sobel(img))
compare(
    "median(disk=3)",
    filters_old.median(img.astype(np.uint8)),
    filters_new.median(img.astype(np.uint8)),
)

canny_old = feature_old.canny(img, sigma=1.5)
canny_new = feature_new.canny(img, sigma=1.5)
compare("canny(sigma=1.5)", canny_old, canny_new)
if not np.array_equal(canny_old, canny_new):
    print(f"           old: {canny_old.sum()} edge pixels  new: {canny_new.sum()} edge pixels")

thresh_old = filters_old.threshold_otsu(img)
thresh_new = filters_new.threshold_otsu(img)
if thresh_old == thresh_new:
    print(f"  EXACT    otsu threshold: {thresh_old}")
else:
    print(f"  DIFFERS  otsu threshold: old={thresh_old}  new={thresh_new}")
