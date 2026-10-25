# Changelog

All notable changes to iCorrVision Grabber are recorded here. Versions follow
[semantic versioning](https://semver.org/).

## Unreleased

- **One installed package.** The code moved into `src/icorrvision_grabber/` and is installed as the
  package `icorrvision_grabber` (distribution `icorrvision-grabber`). 2.0.0 ran from the repository
  folder, whose top-level packages `core`, `UI` and `components` had the same names as those of
  iCorrVision 2D 2.0.0.
- The application starts with `python -m icorrvision_grabber.gui.main` (was `python -m core.main`);
  the devenv `grabber` command does this.
- `pyproject.toml` is the only list of dependencies; `requirements.txt` is removed. Install with
  `pip install .`; VmbPy is the optional extra `allied`, and the notebook dependencies are the extra
  `notebooks`.

## 2.0.0 (tag `v2.0.0-msc`)

First release of iCorrVision Grabber, the image-acquisition application of iCorrVision 2.0 and the
acquisition software of the MSc thesis *iCorrVision 2.0: Development and Metrological Assessment of
Modular Software for Two-Dimensional Digital Image Correlation* (NOVA FCT, 2026).

- Controls OpenCV cameras (webcams and other video devices) and, if VmbPy is installed, Allied
  Vision cameras (Vimba X); two cameras are paired in software.
- Records image series as TIFF files with a `;`-separated CSV manifest, which iCorrVision 2D reads.
- Framing aids: an intensity histogram (optionally restricted to a region of interest), an
  overexposure overlay, and grid, subset-sized square and central target guides.
- Known limitations are listed in the README and in Section 4.5 of the thesis.
