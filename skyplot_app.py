"""
Satellite Constellation Skyplot
  - No-API-key TLE download from CelesTrak (cached locally)
  - No-API-key geocoding via Nominatim (OpenStreetMap)
  - Animated skyplot over a user-defined time range
  - Adjustable playback speed (0.5 – 10 Hz)
  - Save animation as GIF and frame as PNG
"""

import io
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import matplotlib.pyplot as plt
import requests
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from skyfield.api import EarthSatellite, load, wgs84

# ─── Constants ────────────────────────────────────────────────────────────────

CONSTELLATION_GROUPS = {
    "Starlink": "starlink",
    "OneWeb": "oneweb",
    "Iridium NEXT": "iridium-NEXT",
    "GPS": "gps-ops",
    "Galileo": "galileo",
    "GLONASS": "glo-ops",
    "BeiDou": "beidou",
}

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "SkyplotApp/1.0 (no-api-key)",
    "Accept": "application/json,text/plain,*/*",
}

# Light colour palette
BG        = "#f7f9fb"
BG_PANEL  = "#eef2f7"
ACCENT    = "#2563eb"
ACCENT_H  = "#1e40af"
FG        = "#1e293b"
FG_MUTED  = "#64748b"
ENTRY_BG  = "#ffffff"
PLOT_BG   = "#f0f4ff"
PLOT_FACE = "#ffffff"
GRID_CLR  = "#c0cfe8"


# ─── Application ──────────────────────────────────────────────────────────────

class SkyplotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Satellite Constellation Skyplot")
        self.root.geometry("1280x780")
        self.root.configure(bg=BG)

        self._configure_styles()
        self.timescale = load.timescale()

        self.location_var     = tk.StringVar()
        self.start_var        = tk.StringVar(value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        self.end_var          = tk.StringVar(value=(datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"))
        self.increment_var    = tk.StringVar(value="10")
        self.single_var       = tk.BooleanVar(value=False)
        self.constellation_var = tk.StringVar(value="Starlink")
        self.status_var       = tk.StringVar(value="Ready — fill in the form and press Compute.")
        self.speed_var        = tk.DoubleVar(value=2.0)
        self.frame_info_var   = tk.StringVar(value="")

        self._frames: list       = []
        self._current_frame: int = 0
        self._animation_job      = None
        self._running: bool      = False
        self._ac_job             = None
        self._suggestions: list  = []

        self._build_ui()

    # ── Styles ────────────────────────────────────────────────────────────────

    def _configure_styles(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".",          background=BG,       foreground=FG,       font=(None, 10))
        style.configure("TFrame",     background=BG)
        style.configure("TLabel",     background=BG,       foreground=FG)
        style.configure("Muted.TLabel", background=BG,    foreground=FG_MUTED)
        style.configure("TEntry",     fieldbackground=ENTRY_BG, foreground=FG)
        style.configure("TCombobox",  fieldbackground=ENTRY_BG, foreground=FG)
        style.configure("TSpinbox",   fieldbackground=ENTRY_BG, foreground=FG)
        style.configure("TSeparator", background="#d1dce8")

        style.configure("Accent.TButton",
            foreground="#ffffff", background=ACCENT,
            font=(None, 10, "bold"), padding=(10, 6))
        style.map("Accent.TButton",
            foreground=[("active", "#ffffff"), ("disabled", "#9ab0cc")],
            background=[("active", ACCENT_H),  ("disabled", "#b8cfe8")])

        style.configure("Ghost.TButton",
            foreground=ACCENT, background=BG,
            font=(None, 10), padding=(10, 6))
        style.map("Ghost.TButton",
            background=[("active", BG_PANEL)])

    # ── UI Layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(0, weight=0, minsize=315)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=(20, 18, 16, 18))
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(20, weight=1)

        right = ttk.Frame(self.root, padding=(8, 12, 12, 8))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _lbl(self, parent, text, row, muted=False):
        ttk.Label(parent, text=text, style="Muted.TLabel" if muted else "TLabel").grid(
            row=row, column=0, sticky="w", pady=(10, 2))

    def _build_left(self, p):
        ttk.Label(p, text="Satellite Skyplot", font=(None, 14, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(p, text="Configuration", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(0, 12))
        ttk.Separator(p, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self._lbl(p, "Location (city, country)", 3)
        self.location_entry = ttk.Entry(p, textvariable=self.location_var, width=36)
        self.location_entry.grid(row=4, column=0, sticky="ew")
        self.location_entry.bind("<KeyRelease>", self._on_location_changed)

        self.suggestions_list = tk.Listbox(
            p, height=5, width=38,
            bg=ENTRY_BG, fg=FG,
            selectbackground=ACCENT, selectforeground="#ffffff",
            bd=1, relief="flat",
            highlightthickness=1, highlightcolor=ACCENT,
            font=(None, 9))
        self.suggestions_list.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        self.suggestions_list.bind("<<ListboxSelect>>", self._on_suggestion_selected)

        self._lbl(p, "Constellation", 6)
        self.constellation_box = ttk.Combobox(
            p, values=list(CONSTELLATION_GROUPS.keys()),
            textvariable=self.constellation_var, state="readonly", width=33)
        self.constellation_box.grid(row=7, column=0, sticky="ew")

        ttk.Separator(p, orient="horizontal").grid(row=8, column=0, sticky="ew", pady=(14, 2))

        self._lbl(p, "Start date/time UTC  (YYYY-MM-DD HH:MM)", 9)
        self.start_entry = ttk.Entry(p, textvariable=self.start_var, width=36)
        self.start_entry.grid(row=10, column=0, sticky="ew")

        self._lbl(p, "End date/time UTC  (YYYY-MM-DD HH:MM)", 11)
        self.end_entry = ttk.Entry(p, textvariable=self.end_var, width=36)
        self.end_entry.grid(row=12, column=0, sticky="ew")

        self._lbl(p, "Time increment (minutes)", 13)
        inc_frame = ttk.Frame(p)
        inc_frame.grid(row=14, column=0, sticky="w")
        self.inc_spin = ttk.Spinbox(inc_frame, textvariable=self.increment_var,
                from_=1, to=1440, width=8)
        self.inc_spin.grid(row=0, column=0)
        ttk.Label(inc_frame, text="min  — one frame per interval",
              style="Muted.TLabel").grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(p, orient="horizontal").grid(row=15, column=0, sticky="ew", pady=(14, 0))

        ttk.Label(p, textvariable=self.status_var, wraplength=272,
                  style="Muted.TLabel").grid(row=16, column=0, sticky="w", pady=(8, 0))

        self.progress_bar = ttk.Progressbar(p, mode="indeterminate", length=260)
        self.progress_bar.grid(row=17, column=0, sticky="ew", pady=(6, 0))
        self.progress_bar.grid_remove()

        ttk.Frame(p).grid(row=20, column=0, sticky="nsew")

        btn_frame = ttk.Frame(p)
        btn_frame.grid(row=21, column=0, sticky="ew", pady=(16, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        self.compute_btn = ttk.Button(btn_frame, text="▶  Compute",
                                      command=self._start_compute, style="Accent.TButton")
        self.compute_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.save_btn = ttk.Button(btn_frame, text="⬇  Save GIF",
                                   command=self.save_gif, style="Ghost.TButton")
        self.save_btn.grid(row=0, column=1, sticky="ew")
        self.save_btn.state(["disabled"])

        self.save_frame_btn = ttk.Button(btn_frame, text="🖼  Save frame",
                                         command=self.save_frame, style="Ghost.TButton")
        self.save_frame_btn.grid(row=0, column=2, sticky="ew")
        self.save_frame_btn.state(["disabled"])

        # Single-date checkbox
        self.single_cb = ttk.Checkbutton(p, text="Single date / single frame", variable=self.single_var, command=self._on_single_toggled)
        self.single_cb.grid(row=18, column=0, sticky="w", pady=(10, 0))

    def _build_right(self, p):
        info_row = ttk.Frame(p)
        info_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        info_row.columnconfigure(0, weight=0)
        info_row.columnconfigure(1, weight=1)

        # Play / Pause button for animation
        self.play_pause_btn = ttk.Button(info_row, text="⏸ Pause", command=self._toggle_play_pause, style="Accent.TButton")
        self.play_pause_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.play_pause_btn.state(["disabled"])

        ttk.Label(info_row, textvariable=self.frame_info_var,
              style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        self.figure = plt.Figure(figsize=(7, 7), dpi=100, facecolor=PLOT_FACE)
        self.ax = self.figure.add_subplot(111, projection="polar")
        self._style_ax()
        self._draw_empty_plot()

        self.canvas = FigureCanvasTkAgg(self.figure, master=p)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        slider_frame = ttk.Frame(p)
        slider_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        slider_frame.columnconfigure(1, weight=1)

        self.speed_label = ttk.Label(slider_frame, text=f"{self.speed_var.get():.1f} Hz",
              style="Muted.TLabel")
        self.speed_label.grid(row=0, column=0, padx=(0, 8))
        ttk.Scale(slider_frame, from_=0.5, to=10.0, orient="horizontal",
              variable=self.speed_var).grid(row=0, column=1, sticky="ew")
        self.speed_var.trace_add("write", self._on_speed_changed)

    # ── Plot helpers ──────────────────────────────────────────────────────────

    def _style_ax(self):
        self.figure.set_facecolor(PLOT_FACE)
        self.ax.set_facecolor(PLOT_BG)
        self.ax.tick_params(colors=FG_MUTED, labelsize=9)
        for lbl in self.ax.get_yticklabels() + self.ax.get_xticklabels():
            lbl.set_color(FG_MUTED)

    def _draw_empty_plot(self):
        self.ax.clear()
        self._style_ax()
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)
        self.ax.set_rlim(90, 0)
        self.ax.set_rlabel_position(225)
        self.ax.set_yticks([0, 15, 30, 45, 60, 75, 90])
        self.ax.set_yticklabels(
            ["90°", "75°", "60°", "45°", "30°", "15°", "0°"],
            fontsize=8, color=FG_MUTED)
        self.ax.grid(True, color=GRID_CLR, linewidth=0.8)
        self.ax.set_title("Skyplot — compute to start animation", color=FG, pad=14, fontsize=11)
        if hasattr(self, "canvas"):
            self.canvas.draw_idle()

    # ── Location autocomplete ─────────────────────────────────────────────────

    def _on_location_changed(self, _event):
        query = self.location_var.get().strip()
        if len(query) < 2:
            self._set_suggestions([])
            return
        if self._ac_job:
            self.root.after_cancel(self._ac_job)
        self._ac_job = self.root.after(320, lambda: self._request_suggestions(query))

    def _request_suggestions(self, query: str):
        def worker():
            params = {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 8}
            suggestions = []
            try:
                r = requests.get("https://nominatim.openstreetmap.org/search",
                                 params=params, headers=HEADERS, timeout=10)
                r.raise_for_status()
                for item in r.json():
                    addr = item.get("address", {})
                    city = (addr.get("city") or addr.get("town") or
                            addr.get("village") or addr.get("municipality") or
                            addr.get("county"))
                    country = addr.get("country")
                    if city and country:
                        label = f"{city}, {country}"
                    else:
                        parts = [p.strip() for p in
                                 item.get("display_name", "").split(",") if p.strip()]
                        label = ", ".join(parts[:2]) if len(parts) >= 2 else item.get("display_name", "")
                    if label and label not in suggestions:
                        suggestions.append(label)
            except Exception:
                pass
            self.root.after(0, lambda: self._set_suggestions(suggestions))
        threading.Thread(target=worker, daemon=True).start()

    def _set_suggestions(self, suggestions):
        self._suggestions = suggestions
        self.suggestions_list.delete(0, tk.END)
        for item in suggestions:
            self.suggestions_list.insert(tk.END, item)

    def _on_suggestion_selected(self, _event):
        sel = self.suggestions_list.curselection()
        if sel:
            self.location_var.set(self._suggestions[sel[0]])

    # ── Speed slider ──────────────────────────────────────────────────────────

    def _on_speed_changed(self, *_):
        self.speed_label.configure(text=f"{self.speed_var.get():.1f} Hz")

    # ── Input helpers ─────────────────────────────────────────────────────────

    def _parse_dt(self, value: str, label: str) -> datetime:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        raise ValueError(f"{label}: use YYYY-MM-DD HH:MM (UTC) or YYYY-MM-DD.")

    def _geocode(self, location: str):
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "jsonv2", "limit": 1},
            headers=HEADERS, timeout=12)
        r.raise_for_status()
        data = r.json()
        if not data:
            raise ValueError(f"Location not found: '{location}'")
        return float(data[0]["lat"]), float(data[0]["lon"])

    # ── TLE management ────────────────────────────────────────────────────────

    def _find_cached_tle(self, constellation: str) -> Path | None:
        matches = sorted(DATA_DIR.glob(f"TLE_{constellation.upper()}_*"))
        return matches[-1] if matches else None

    def _download_tle(self, constellation: str) -> Path:
        group = CONSTELLATION_GROUPS[constellation]
        url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle"
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        content = r.text.strip()
        if not content:
            raise ValueError("CelesTrak returned an empty TLE file.")
        now = datetime.now(timezone.utc)
        target = DATA_DIR / f"TLE_{constellation.upper()}_{now:%y%m%d}"
        target.write_text(content + "\n", encoding="utf-8")
        return target

    def _get_tle_file(self, constellation: str) -> tuple[Path, bool]:
        existing = self._find_cached_tle(constellation)
        if existing:
            return existing, False
        return self._download_tle(constellation), True

    def _parse_tle(self, text: str) -> list[EarthSatellite]:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        sats, i = [], 0
        while i + 2 < len(lines):
            n, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
            if l1.startswith("1 ") and l2.startswith("2 "):
                sats.append(EarthSatellite(l1, l2, n, self.timescale))
                i += 3
            else:
                i += 1
        return sats

    # ── Computation ───────────────────────────────────────────────────────────

    def _start_compute(self):
        self._stop_animation()
        location = self.location_var.get().strip()
        if "," not in location:
            messagebox.showerror("Input error", "Location must be 'city, country'.")
            return
        constellation = self.constellation_var.get()
        try:
            start_dt = self._parse_dt(self.start_var.get(), "Start date")
            end_dt = self._parse_dt(self.end_var.get(), "End date")
            inc_min = int(self.increment_var.get())
        except ValueError as e:
            messagebox.showerror("Input error", str(e))
            return

        if self.single_var.get():
            timestamps = [start_dt]
            n_frames = 1
        else:
            if end_dt <= start_dt:
                messagebox.showerror("Input error", "End date must be after Start date.")
                return
            if inc_min < 1:
                messagebox.showerror("Input error", "Increment must be ≥ 1 minute.")
                return
            timestamps = []
            t = start_dt
            while t <= end_dt:
                timestamps.append(t)
                t += timedelta(minutes=inc_min)
            n_frames = len(timestamps)

        if n_frames > 2000:
            if not messagebox.askyesno("Warning",
                    f"That's {n_frames} frames — this may take a while. Continue?"):
                return

        self.compute_btn.state(["disabled"])
        self.save_btn.state(["disabled"])
        self.progress_bar.grid()
        self.progress_bar.start(12)
        self._frames = []
        self._set_status(f"Resolving location…")

        def worker():
            try:
                lat, lon = self._geocode(location)
                self._set_status("Loading TLE data…")
                tle_file, downloaded = self._get_tle_file(constellation)
                sats = self._parse_tle(tle_file.read_text(encoding="utf-8"))
                if not sats:
                    raise ValueError("No valid satellites found in TLE file.")

                self._set_status(f"Computing {n_frames} frames × {len(sats)} satellites…")
                observer = wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
                ts_array = self.timescale.from_datetimes(timestamps)

                frames: list[list] = [[] for _ in timestamps]
                for sat in sats:
                    topo = (sat - observer).at(ts_array)
                    alts, azs, _ = topo.altaz()
                    for i, (a, z) in enumerate(zip(alts.degrees, azs.degrees)):
                        if a > 0:
                            frames[i].append((sat.name, float(a), float(z)))

                result = list(zip(timestamps, frames))
                src = "downloaded" if downloaded else "cached"
                max_vis = max((len(f) for f in frames), default=0)

                def on_done():
                    self._frames = result
                    self._current_frame = 0
                    self.progress_bar.stop()
                    self.progress_bar.grid_remove()
                    self.compute_btn.state(["!disabled"])
                    self.save_btn.state(["!disabled"])
                    self.save_frame_btn.state(["!disabled"])
                    self.play_pause_btn.state(["!disabled"])
                    self.play_pause_btn.configure(text="⏸ Pause")
                    self._set_status(
                        f"{n_frames} frames computed | max {max_vis} visible | TLE: {src} ({tle_file.name})")
                    self._start_animation()
                self.root.after(0, on_done)

            except Exception as exc:
                def on_err():
                    self.progress_bar.stop()
                    self.progress_bar.grid_remove()
                    self.compute_btn.state(["!disabled"])
                    self._set_status("Error — see dialog.")
                    messagebox.showerror("Computation error", str(exc))
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _start_animation(self):
        self._stop_animation()
        if not self._frames:
            return
        self._running = True
        self._tick()

    def _stop_animation(self):
        self._running = False
        if self._animation_job is not None:
            self.root.after_cancel(self._animation_job)
            self._animation_job = None

    def _tick(self):
        if not self._running or not self._frames:
            return
        self._render_frame(self._current_frame)
        self._current_frame = (self._current_frame + 1) % len(self._frames)
        delay_ms = max(50, int(1000 / self.speed_var.get()))
        self._animation_job = self.root.after(delay_ms, self._tick)

    def _render_frame(self, idx: int):
        import math
        when_utc, points = self._frames[idx]
        constellation = self.constellation_var.get()
        location = self.location_var.get().strip()

        self.ax.clear()
        self._style_ax()
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)
        self.ax.set_rlim(90, 0)
        self.ax.set_rlabel_position(225)
        self.ax.set_yticks([0, 15, 30, 45, 60, 75, 90])
        self.ax.set_yticklabels(
            ["90°", "75°", "60°", "45°", "30°", "15°", "0°"],
            fontsize=8, color=FG_MUTED)
        self.ax.grid(True, color=GRID_CLR, linewidth=0.8)

        if points:
            theta = [z * math.pi / 180 for _, _, z in points]
            r     = [90 - a          for _, a, _ in points]
            self.ax.scatter(theta, r, s=28, color=ACCENT, alpha=0.80, zorder=3)
            for i in range(min(30, len(points))):
                self.ax.text(theta[i], r[i], points[i][0],
                             fontsize=7, color=FG_MUTED, alpha=0.7,
                             ha="center", va="bottom")

        self.ax.set_title(
            f"{constellation}  |  {when_utc:%Y-%m-%d %H:%M UTC} \n"
            f"{location}  |  {len(points)} visible",
            color=FG, pad=14, fontsize=10)
        self.frame_info_var.set(f"Frame {idx + 1} / {len(self._frames)}")
        self.canvas.draw_idle()

    # ── Single-date toggle ───────────────────────────────────────────────────

    def _on_single_toggled(self):
        single = self.single_var.get()
        state = "disabled" if single else "normal"
        try:
            self.end_entry.configure(state=state)
            self.inc_spin.configure(state=state)
        except Exception:
            pass
        if single:
            self._set_status("Single-date mode enabled: end/increment disabled.")
        else:
            self._set_status("Range mode enabled: end/increment enabled.")

    # ── Play / Pause ────────────────────────────────────────────────────────

    def _toggle_play_pause(self):
        if not self._frames:
            return
        if self._running:
            self._stop_animation()
            self.play_pause_btn.configure(text="▶ Play")
            self._set_status("Paused")
        else:
            self._start_animation()
            self.play_pause_btn.configure(text="⏸ Pause")
            self._set_status("Running")

    # ── Save single frame ───────────────────────────────────────────────────

    def save_frame(self):
        if not self._frames:
            messagebox.showinfo("No data", "Compute an animation first.")
            return
        # choose the currently displayed frame
        if self._running:
            idx = (self._current_frame - 1) % len(self._frames)
        else:
            idx = self._current_frame
        when_utc, points = self._frames[idx]

        default_name = f"skyplot_frame_{when_utc:%y%m%d_%H%M}.png"
        path = filedialog.asksaveasfilename(defaultextension=".png",
                                            filetypes=[("PNG image", "*.png"), ("All files", "*")],
                                            initialfile=default_name)
        if not path:
            return

        try:
            import math
            # render into the figure
            self.ax.clear()
            self._style_ax()
            self.ax.set_theta_zero_location("N")
            self.ax.set_theta_direction(-1)
            self.ax.set_rlim(90, 0)
            self.ax.set_rlabel_position(225)
            self.ax.set_yticks([0, 15, 30, 45, 60, 75, 90])
            self.ax.set_yticklabels(["90°", "75°", "60°", "45°", "30°", "15°", "0°"], fontsize=8, color=FG_MUTED)
            self.ax.grid(True, color=GRID_CLR, linewidth=0.8)

            if points:
                theta = [z * math.pi / 180 for _, _, z in points]
                r = [90 - a for _, a, _ in points]
                self.ax.scatter(theta, r, s=28, color=ACCENT, alpha=0.80, zorder=3)
                for i in range(min(30, len(points))):
                    self.ax.text(theta[i], r[i], points[i][0], fontsize=7, color=FG_MUTED, alpha=0.7, ha="center", va="bottom")

            # set title consistent with on-screen frame
            constellation = self.constellation_var.get()
            location = self.location_var.get().strip()
            self.ax.set_title(
                f"{constellation}  |  {len(points)} visible\n"
                f"{when_utc:%Y-%m-%d %H:%M UTC}  —  {location}",
                color=FG, pad=14, fontsize=10,
            )

            self.figure.savefig(path, dpi=200, facecolor=PLOT_FACE, bbox_inches="tight")
            messagebox.showinfo("Saved", f"Frame saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    # ── Save GIF ──────────────────────────────────────────────────────────────

    def save_gif(self):
        if not self._frames:
            messagebox.showinfo("No data", "Compute an animation first.")
            return
        try:
            from PIL import Image
        except ImportError:
            messagebox.showerror("Missing dependency",
                "Pillow is required to save GIFs.\nRun:  pip install Pillow")
            return

        constellation = self.constellation_var.get()
        default_name = f"skyplot_{constellation}_{datetime.utcnow():%y%m%d_%H%M}.gif"
        path = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF animation", "*.gif"), ("All files", "*")],
            initialfile=default_name)
        if not path:
            return

        self._stop_animation()
        total = len(self._frames)
        location = self.location_var.get().strip()
        self._set_status("Rendering GIF…")

        def worker():
            import math
            pil_frames = []
            for idx, (when_utc, points) in enumerate(self._frames):
                self.ax.clear()
                self._style_ax()
                self.ax.set_theta_zero_location("N")
                self.ax.set_theta_direction(-1)
                self.ax.set_rlim(90, 0)
                self.ax.set_rlabel_position(225)
                self.ax.grid(True, color=GRID_CLR, linewidth=0.8)
                if points:
                    theta = [z * math.pi / 180 for _, _, z in points]
                    r     = [90 - a          for _, a, _ in points]
                    self.ax.scatter(theta, r, s=24, color=ACCENT, alpha=0.85)
                    for i in range(min(30, len(points))):
                        self.ax.text(theta[i], r[i], points[i][0], fontsize=7, color=FG_MUTED, alpha=0.7, ha="center", va="bottom")
                self.ax.set_title(
                    f"{constellation}  |  {len(points)} visible\n"
                    f"{when_utc:%Y-%m-%d %H:%M UTC}  —  {location}",
                    color=FG, pad=14, fontsize=10)
                buf = io.BytesIO()
                self.figure.savefig(buf, format="png", dpi=120, facecolor=PLOT_FACE)
                buf.seek(0)
                pil_frames.append(Image.open(buf).copy())
                if idx % 10 == 0:
                    self.root.after(0, lambda i=idx: self._set_status(
                        f"Rendering frame {i + 1}/{total}…"))

            duration_ms = max(50, int(1000 / max(0.5, self.speed_var.get())))
            pil_frames[0].save(path, save_all=True,
                               append_images=pil_frames[1:],
                               loop=0, duration=duration_ms, optimize=False)

            def on_done():
                self._set_status(f"GIF saved: {Path(path).name}")
                self._start_animation()
                messagebox.showinfo("Saved", f"Animation saved to:\n{path}")
            self.root.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    SkyplotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
