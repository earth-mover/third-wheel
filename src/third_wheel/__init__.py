"""Third Wheel - A tool to rename Python wheel packages for multi-version installation."""

from third_wheel._version import __version__
from third_wheel.patch import patch_wheel
from third_wheel.rename import rename_wheel

__all__ = ["__version__", "patch_wheel", "rename_wheel"]
