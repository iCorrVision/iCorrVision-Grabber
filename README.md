# iCorrVision Grabber

The image-acquisition application of iCorrVision 2.0. It controls cameras, records image series
as TIFF files with a CSV manifest, and provides framing aids: an intensity histogram (optionally
restricted to a region of interest), an overexposure overlay, and grid, subset-sized square and
central target guides. Series it saves are read by
[iCorrVision 2D](https://github.com/iCorrVision/iCorrVision-2D), the correlation application.

This is the acquisition software of the MSc thesis *iCorrVision 2.0: Development and Metrological
Assessment of Modular Software for Two-Dimensional Digital Image Correlation* (João Pedro da Silva
Duarte Récio, NOVA FCT, 2026), supervised by José Manuel Cardoso Xavier. The tag `v2.0.0-msc` is
the version the thesis cites.

> [!WARNING]
> **OpenCV cameras: recordings start and stop late.** The OpenCV backend requests a frame at every
> tick of its poll timer, whether or not the previous request has been served. When the timer is
> faster than the camera, the requests queue up and Record and Stop wait behind them, so a recording
> starts and ends late by a delay that grows with the preview time: in the thesis tests, 0.13 s
> after 2 s of preview and more than 10 s when the poll rate was above the camera's rate. Images
> saved after Stop have no manifest row. Do not use the OpenCV backend for measurements in this
> version.

> [!WARNING]
> **Failures are not reported.** A camera that fails during a recording is only logged to the
> console, and the recording continues; a failed image write is not detected, and the manifest then
> lists images that do not exist. Check every series against its manifest before using it.

## Install and run

Python 3.12 or newer. Use a virtual environment of its own: the Grabber and iCorrVision 2D both
have top-level packages named `core`, `UI` and `components`, so they must not be installed into
the same environment.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m core.main
```

On NixOS, `devenv shell` provides the environment, and the `grabber` command starts the application
with the Qt libraries it needs.

## Cameras

- **OpenCV (webcams and other video devices):** works out of the box. Device discovery is
  implemented for Linux only. The backend sets no capture property: OpenCV requests 640 × 480
  pixels at 30 fps, and exposure, gain and focus stay as the driver sets them. The FPS box sets the
  poll rate, not the camera's frame rate.
- **Allied Vision (Vimba X):** optional. Install the
  [Vimba X SDK](https://www.alliedvision.com/en/support/software-downloads/vimba-x-sdk/vimba-x) and then VmbPy
  (`pip install vmbpy`, or the wheel shipped in the SDK under `api/python/`). The Allied Vision
  panel appears only if VmbPy can be imported; without it the application runs with OpenCV
  cameras only. Cameras are opened in 8-bit greyscale (Mono8). Settings saved to a
  `<serial number>.xml` file are loaded into the camera with that serial number; since the camera
  is streaming, not every setting is necessarily applied (with the camera simulator, the pixel
  format was not), and a setting that is not applied is not reported.

## Saved series

- **Images:** `<prefix>_<camera index>_<frame number>.tiff` (four-digit frame number, e.g.
  `frame_0_0012.tiff`). The next number is found by scanning the folder at each Record and each
  Snapshot, so numbering continues from the files already there.
- **Manifest:** `<prefix>.csv` in the same folder, `;`-separated: `date`, then per camera
  `<label>_frame_time` (seconds since recording started) and `<label>_frame_name`, with label
  `left` for camera 0 and `right` for camera 1. One row per frame, or per pair in two-camera mode.
  Recordings and snapshots under the same prefix are added to the same manifest; the elapsed time
  restarts at each Record.

iCorrVision 2D lists the frames of a series in acquisition order from this manifest; images
without a manifest row are ignored there, but not by its command-line interface, which selects
images by name.

Connect the cameras first, then set the save folder and prefix, then record: a prefix set before a
camera is connected names the manifest but not that camera's images, and changing folder or prefix
while recording is not supported. The overexposure threshold slider shows 255 at start-up, but 200
is used until the slider is moved.

## Known limitations

The thesis lists them in Section 4.5 and Table 4.3; they are to be corrected in a later version.

- Camera settings are not recorded in the manifest. Times are software timestamps, taken when a
  frame reaches the interface thread, so they include its load.
- If the writer falls behind the camera, restarting a recording or taking a snapshot reuses frame
  numbers: the later image overwrites the earlier one and the manifest lists the name twice. The
  writer queue has no size limit, so that no frame is dropped or delayed; the cost is memory.
- Frames already acquired but not yet handled by the interface when Stop is pressed are saved
  without a manifest row. Closing the application during a recording can lose its last frames. A
  snapshot taken while OpenCV polling is off gets its row only when the next frame arrives.
- Two cameras are paired in software, without a hardware trigger. A frame still waiting for its
  pair when a recording stops is left out of its manifest and can open the manifest of the next
  recording.
- The Record button shows a recording in progress when no save folder is set, and after the camera
  mode is changed during a recording, although nothing is saved. Settings changed before a camera
  is connected (prefix, overlay, OpenCV greyscale, Allied Vision exposure and frame rate) are not
  applied to it.
- With the overlay on, the framing guides are drawn at the scale of the reduced overlay image
  (twice their size at the default "Overlay downscaling"), and the subset square has no outline.
  The overexposed-pixel count also refers to the reduced frame, not the full-resolution one.
- The histogram keeps its region of interest after a change of camera mode, and "Match ROI" before
  a region is drawn ends with an error.

## Benchmarks

`benchmarks/acquisition_check.ipynb` checks recorded series: integrity, frame count, intervals
between frames and, for two cameras, the pairing offset. It keeps the outputs of the thesis runs
and ends with a guide to reading them. The recordings and the runs table are not distributed,
since `.gitignore` excludes image series and CSV files. To check new recordings, install the
notebook dependencies from `requirements.txt`, list the recordings in `acquisition_runs.csv` (the
first cell describes its columns) and run the notebook from the `benchmarks/` folder.

## Tested with

The acquisition test of the thesis used Python 3.12.13, PySide6 6.10.2, OpenCV 5.0.0 and NumPy
2.5.3 on NixOS (Linux) for the OpenCV backend, and Python 3.12.3, PySide6 6.10.2, OpenCV 4.13.0,
NumPy 2.4.4, VmbPy 1.2.1 and Vimba X 2026-1 on Ubuntu 24.04 for the Allied Vision backend, with
simulated cameras (Section 5.3.5 of the thesis). `requirements.txt` gives lower bounds only
(except PySide6), so a new installation may use newer versions.

## Citation

See `CITATION.cff`, or use GitHub's "Cite this repository" button.

## Licence

GPL-3.0-or-later; see `LICENSE`.
