# Satellite Constellation Skyplot

A small desktop app to download constellation TLEs (no API key), compute satellite positions for a given location/time range, and display an animated skyplot. Includes features to autocomplete city names (OpenStreetMap Nominatim), cache TLEs under `data/`, save single frames (PNG) and save animated GIFs.

## Quick summary
- Script: `skyplot_app.py`
- TLE cache folder: `data/` (created automatically)
- Dependencies listed in `requirements.txt`

## Prerequisites
- Python 3.10+ (3.11 or 3.12 recommended)
- Internet access for geocoding (Nominatim) and TLE download (CelesTrak)

Optional system packages (Linux) if you encounter GUI issues:
- Debian/Ubuntu: `sudo apt install python3-tk` (Tkinter for tkinter) and required libs for matplotlib

## Install and run (recommended: virtual environment)

Linux / macOS (bash/zsh):

```bash
# 1) Install Python 3.11+ if not installed
# 2) create a virtual environment inside the project
python3 -m venv .venv
# 3) activate the venv
source .venv/bin/activate
# 4) upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
# 5) run the app
python skyplot_app.py
```

Windows (PowerShell):

```powershell
# 1) Install Python 3.11+ from python.org
# 2) create venv
python -m venv .venv
# 3) activate
.\.venv\Scripts\Activate.ps1
# 4) install deps
python -m pip install --upgrade pip
pip install -r requirements.txt
# 5) run
python skyplot_app.py
```

## What the app does
- Enter `Location` in `city, country` format (the field autocompletes using OpenStreetMap Nominatim once you type 2+ characters).
- Choose a `Constellation` (Starlink, OneWeb, GPS, Galileo, etc.).
- Choose either a single date (enable "Single date / single frame") or a Start + End + increment (minutes) to produce an animation of multiple frames.
- Press `Compute` to geocode, download (or re-use cached) TLEs, pre-compute frames and start the animation.
- Use the speed slider to adjust playback rate (0.5–10 Hz). Use the Play/Pause button to pause/resume.
- Use `Save frame` to export the currently-displayed frame as a PNG (title and satellite labels included).
- Use `Save GIF` to export the full animation as an animated GIF (requires Pillow).

Notes about TLE caching
- TLE files are saved under `data/` as `TLE_<CONST>_YYMMDD`. If a matching file exists it will be reused rather than redownloaded.

Nominatim usage / etiquette
- The app uses OpenStreetMap Nominatim for geocoding without an API key. Please be polite with request frequency and set a descriptive `User-Agent` (the app already does this).

Troubleshooting
- If the GUI fails to launch on Linux, ensure Tkinter is installed (`sudo apt install python3-tk`).
- If matplotlib cannot display, ensure you have the required GUI backend and system libraries installed.
- If `Pillow` is missing when saving GIFs, install it: `pip install Pillow`.

License
- This project is licensed under the MIT License.
