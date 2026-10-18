"""iCorrVision 2.0 Grabber: image acquisition for digital image correlation.

The package has no public API: it is the application, started with
``python -m icorrvision_grabber.gui.main``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read from the installed distribution's metadata so the version is written
    # once, in pyproject.toml. Running from a source checkout without installing
    # has no metadata to read, hence the fallback.
    __version__ = version("icorrvision-grabber")
except PackageNotFoundError:
    __version__ = "unknown (not installed)"
