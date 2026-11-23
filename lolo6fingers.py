#!/usr/bin/env python3
"""LoLo6Fingers — a YouTube & Instagram downloader for macOS, built on yt-dlp.

Made with editing in Adobe Premiere in mind: it can automatically re-encode
AV1/VP9 videos to H.264, using the GPU when available.
"""
import os
import re
import sys
import glob
import json
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    raise SystemExit("Error: the yt-dlp library is not installed. Run setup.command first.")

try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

if getattr(sys, "frozen", False):
    FFMPEG_DIR = sys._MEIPASS
else:
    FFMPEG_DIR = None
    for _c in ("/opt/homebrew/bin", "/usr/local/bin"):
        if os.path.isdir(_c) and _c not in os.environ.get("PATH", ""):
            os.environ["PATH"] = _c + os.pathsep + os.environ.get("PATH", "")

APP_NAME = "LoLo6Fingers"
VERSION = "4.3"

# Fallback YouTube clients. They are used ONLY after the standard attempt
# fails — never as a hardcoded default. Hardcoding clients (especially
# web / web_safari together with cookies) once broke every download with
# "The page needs to be reloaded".
#
# Chosen from the INNERTUBE_CLIENTS table in yt-dlp 2026.10.x:
#   - tv, tv_downgraded, web_embedded: do NOT need a PO token, support
#     cookies, need a JS runtime. yt-dlp does not try them on its own
#     (its defaults are tv_samsung, visionos, web), so they are real
#     extra chances.
#   - mweb, web_safari, android, ios: return no video data WITHOUT a PO
#     token, so they are only worth trying when a provider is installed.
_CLIENTS_NO_POT = ["tv", "tv_downgraded", "web_embedded"]
_CLIENTS_NEED_POT = ["mweb", "web_safari", "android", "ios"]

# Codecs Adobe Premiere (and QuickTime) cannot read. AV1 and VP9 are common
# on YouTube and Facebook, so a downloaded file can be technically fine
# but unusable in an editor.
_INCOMPATIBLE_CODECS = ("av01", "av1", "vp9", "vp09", "vp8")

_GPU_CACHE = None


def _find_js_runtimes():
    """Find a JavaScript runtime for yt-dlp. YouTube sends signature and
    'n' challenges in JavaScript and without a runtime yt-dlp cannot solve
    them — it says so itself: 'extraction without a JS runtime has been
    deprecated, and some formats may be missing'. Worse, without one it
    only tries a single client (visionos). By default yt-dlp looks ONLY for
    deno, so an installed Node.js would otherwise go unused.
    The bundled .app has no Homebrew PATH, so we also check fixed paths."""
    home = os.path.expanduser("~")

    def _nvm_key(p):
        m = re.search(r"/v(\d+)\.(\d+)\.(\d+)/", p)
        return tuple(int(x) for x in m.groups()) if m else (0,)

    # Deno bundled inside the .app wins — most users have neither Node nor Deno
    bundled = [os.path.join(sys._MEIPASS, "deno")] if getattr(sys, "frozen", False) else []
    candidates = {
        "deno": bundled + [shutil.which("deno"), f"{home}/.deno/bin/deno",
                           "/opt/homebrew/bin/deno", "/usr/local/bin/deno"],
        "node": [shutil.which("node"), "/opt/homebrew/bin/node", "/usr/local/bin/node"]
                + sorted(glob.glob(f"{home}/.nvm/versions/node/*/bin/node"),
                         key=_nvm_key, reverse=True),
    }
    found = {}
    for name, paths in candidates.items():
        for p in paths:
            if not (p and os.path.isfile(p) and os.access(p, os.X_OK)):
                continue
            # yt-dlp silently ignores runtimes that are too old (Node 20/21
            # would be "accepted" but never used), so we check the version.
            v = _runtime_version(p)
            if v and v >= _MIN_JS_VERSION[name]:
                found[name] = {"path": p}
                _JS_VERSIONS[name] = ".".join(map(str, v))
                break
    # Nothing found — keep yt-dlp's default behaviour (deno)
    return found or {"deno": {}}


# Minimum versions, from yt_dlp/utils/_jsruntime.py (2026.10.x)
_MIN_JS_VERSION = {"deno": (2, 3, 0), "node": (22, 0, 0)}
_JS_VERSIONS = {}


def _runtime_version(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True,
                             text=True, timeout=10).stdout
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        return tuple(int(x) for x in m.groups()) if m else None
    except Exception:
        return None


_JS_RUNTIMES = _find_js_runtimes()


def _js_runtime_status():
    with_path = [f"{name} {_JS_VERSIONS.get(name, '')}".strip()
                 + (" (bundled)" if getattr(sys, "frozen", False)
                    and cfg["path"].startswith(getattr(sys, "_MEIPASS", "\0")) else "")
                 for name, cfg in _JS_RUNTIMES.items() if cfg.get("path")]
    if with_path:
        return "✅ " + ", ".join(with_path)
    return ("❌ not found — YouTube tries only 1 client, many videos will fail "
            "(install Deno or Node 22+)")


def _gpu_encoder(ffmpeg_bin):
    """Detect once whether ffmpeg has a hardware H.264 encoder (VideoToolbox
    on macOS, NVENC/QuickSync on Windows). The result is cached."""
    global _GPU_CACHE
    if _GPU_CACHE is not None:
        return _GPU_CACHE
    try:
        out = subprocess.run([ffmpeg_bin, "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=15).stdout
        if "h264_videotoolbox" in out:
            _GPU_CACHE = "h264_videotoolbox"
        elif "h264_nvenc" in out:
            _GPU_CACHE = "h264_nvenc"
        elif "h264_qsv" in out:
            _GPU_CACHE = "h264_qsv"
        else:
            _GPU_CACHE = ""
    except Exception:
        _GPU_CACHE = ""
    return _GPU_CACHE


def _path_from_info(info):
    """Get the real path of the downloaded file from a yt-dlp info dict.
    After merging video+audio the name differs from prepare_filename(),
    so we read 'requested_downloads'."""
    if not info:
        return None
    try:
        rd = info.get("requested_downloads")
        if rd:
            return rd[0].get("filepath") or rd[0].get("_filename")
        return info.get("filepath") or info.get("_filename")
    except Exception:
        return None


def _error_gist(stderr_text):
    """Pick the line of ffmpeg output that actually explains the failure.
    ffmpeg prints dozens of banner and metadata lines — without this the
    useful information would get lost."""
    interesting = ("Error", "error", "Invalid", "not supported", "Unsupported",
                   "failed", "Failed", "No such", "Cannot", "cannot")
    lines = [r.strip() for r in stderr_text.splitlines() if r.strip()]
    for r in reversed(lines):
        if any(z in r for z in interesting):
            return r[:160]
    return lines[-1][:160] if lines else "unknown reason"


def _video_codec(ffprobe_bin, path):
    """Return the file's video codec name, or '' when it cannot be detected."""
    try:
        out = subprocess.run(
            [ffprobe_bin, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", path],
            capture_output=True, text=True, timeout=30,
        ).stdout
        streams = json.loads(out).get("streams", [])
        if streams:
            return (streams[0].get("codec_name") or "").lower()
    except Exception:
        pass
    return ""


def _chrome_profiles():
    """Find Chrome profiles together with their readable names.
    Otherwise yt-dlp always reads the 'Default' profile — when the user is
    signed in under another profile, cookies load but do not grant access."""
    base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    if not os.path.isdir(base):
        return []

    # Readable profile names live in the 'Local State' file
    names = {}
    try:
        with open(os.path.join(base, "Local State"), encoding="utf-8") as f:
            info_cache = json.load(f).get("profile", {}).get("info_cache", {}) or {}
        for folder, info in info_cache.items():
            name = info.get("name") or info.get("gaia_name") or ""
            if name:
                names[folder] = name
    except Exception:
        pass

    profiles = []
    try:
        for entry in sorted(os.listdir(base)):
            path = os.path.join(base, entry)
            if not os.path.isdir(path):
                continue
            if entry != "Default" and not entry.startswith("Profile "):
                continue
            # A profile is only usable if it has a cookies database
            has_cookies = (os.path.exists(os.path.join(path, "Cookies"))
                           or os.path.exists(os.path.join(path, "Network", "Cookies")))
            if not has_cookies:
                continue
            name = names.get(entry)
            label = f"{name}  ({entry})" if name else entry
            profiles.append((label, entry))
    except Exception:
        pass
    return profiles


def _pot_parts():
    """Return (plugin_found, provider_found) for the PO Token provider."""
    try:
        import importlib.util
        plugin = bool(importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil")
                      or importlib.util.find_spec("bgutil_ytdlp_pot_provider"))
    except Exception:
        plugin = False
    server = os.path.isdir(os.path.expanduser("~/bgutil-ytdlp-pot-provider/server/build"))
    return plugin, server


def _pot_provider_active():
    plugin, server = _pot_parts()
    return plugin and server


def _pot_provider_status():
    """Is the PO Token provider installed? Without it YouTube sends only
    storyboards instead of real video for many videos."""
    plugin, server = _pot_parts()
    if plugin and server:
        return "✅ active"
    if plugin and not server:
        return "⚠︎ plugin found, provider missing — run setup-potoken.command"
    if server and not plugin:
        return "⚠︎ provider found, plugin missing — run setup-potoken.command"
    return "❌ not installed (run setup-potoken.command)"


def _version_numbers(v):
    """Turn '2026.10.10.233141.dev0' into [2026, 10, 10, 233141].
    Nightly versions have more parts than stable ones, so comparing the
    strings is not enough."""
    numbers = []
    for part in str(v).split("."):
        part = part.split("dev")[0]
        if part.isdigit():
            numbers.append(int(part))
    return numbers


def _latest_ytdlp():
    """Return (latest_stable, latest_overall) from PyPI.
    NOTE: originally only the stable version was checked. On a nightly
    build a newer nightly went unnoticed — and stable releases can be
    months apart."""
    try:
        import urllib.request
        with urllib.request.urlopen(
                "https://pypi.org/pypi/yt-dlp/json", timeout=8) as r:
            data = json.load(r)
        stable = data["info"]["version"]
        everything = list((data.get("releases") or {}).keys())
        overall = max(everything, key=_version_numbers) if everything else stable
        return stable, overall
    except Exception:
        return "", ""


def _is_newer(current, latest):
    """Compare versions numerically, part by part (handles nightlies too)."""
    try:
        a = _version_numbers(current)
        b = _version_numbers(latest)
        return bool(a) and bool(b) and b > a
    except Exception:
        return False


def _parse_progress(line):
    """Extract (processed_seconds, speed) from an 'ffmpeg -progress' line.
    Depending on version ffmpeg sends out_time_us, out_time_ms or out_time.
    Careful: out_time_ms is historically in MICROseconds, not milliseconds."""
    line = line.strip()
    try:
        if line.startswith("out_time_us="):
            v = line.split("=", 1)[1]
            return (int(v) / 1_000_000, None) if v.strip("-").isdigit() else (None, None)
        if line.startswith("out_time_ms="):
            v = line.split("=", 1)[1]
            return (int(v) / 1_000_000, None) if v.strip("-").isdigit() else (None, None)
        if line.startswith("out_time="):
            hh, mm, ss = line.split("=", 1)[1].split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss), None
        if line.startswith("speed="):
            return None, float(line.split("=", 1)[1].strip().rstrip("x") or 0)
    except (ValueError, IndexError):
        pass
    return None, None


def _bitrate_for_height(h):
    """Hardware encoders work with a bitrate, not CRF. The values are high
    enough for editing (Premiere)."""
    if h >= 2160:
        return "55M", "75M"
    if h >= 1440:
        return "32M", "45M"
    if h >= 1080:
        return "18M", "25M"
    return "10M", "14M"


FORMATS = {
    "Automatic (recommended for Instagram/Facebook)": "AUTO",
    # Every selector cascades: exact H.264 match -> H.264 at a lower
    # resolution -> any codec -> anything. Without the fallbacks yt-dlp
    # fails with "Requested format is not available" on videos that do
    # not offer H.264 at that resolution.
    "Best H.264 (MP4, for Premiere)":
        "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/best[vcodec^=avc1]"
        "/bestvideo+bestaudio/best",
    "4K – re-encoded to H.264 (for Premiere, slow)": "RECODE_4K",
    "4K original (VP9/AV1, for viewing)":
        "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
    "1080p H.264 (MP4)":
        "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]"
        "/best[height<=1080][vcodec^=avc1]"
        "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p H.264 (MP4)":
        "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]"
        "/best[height<=720][vcodec^=avc1]"
        "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p H.264 (MP4)":
        "bestvideo[height<=480][vcodec^=avc1]+bestaudio[ext=m4a]"
        "/best[height<=480][vcodec^=avc1]"
        "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "Re-encode to H.264 (universal, slower)": "RECODE_H264",
    "Audio only (MP3)": "AUDIO_MP3",
}


def _is_youtube(url):
    u = url.lower()
    return ("youtube.com" in u) or ("youtu.be" in u)


def _looks_blocked(msg):
    """Errors where trying other clients makes sense. HTTP 403 during a
    download usually means a missing PO token or a URL that YouTube has
    invalidated — another client gets a fresh one."""
    return ("not available" in msg or "Video unavailable" in msg
            or "Sign in to confirm" in msg or "players" in msg.lower()
            or "HTTP Error 403" in msg)


def _is_persistent_error(msg):
    """Errors that will not change if the same attempt is repeated right
    away. Network failures (timeout, DNS) intentionally do not belong here."""
    return (_looks_blocked(msg)
            or "Please sign in" in msg or "Private video" in msg
            or "members-only" in msg.lower() or "DRM" in msg
            or "Unsupported URL" in msg)


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} {VERSION} – YouTube & Instagram downloader by Norrislav")
        root.geometry("820x470")
        root.minsize(760, 450)
        self.dest = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.fmt = tk.StringVar(value=list(FORMATS.keys())[0])
        self.use_cookies = tk.BooleanVar(value=False)
        self.use_gpu = tk.BooleanVar(value=True)
        self.premiere_compat = tk.BooleanVar(value=True)
        try:
            _ytv = yt_dlp.version.__version__
        except Exception:
            _ytv = "?"
        self._ytdlp_version = _ytv
        self.status = tk.StringVar(
            value=f"Ready.   (version {VERSION} · yt-dlp {_ytv})")
        self._cancel_event = threading.Event()
        self._ffmpeg_proc = None
        self._encoder_used = "libx264"
        self._gpu_fail_reason = ""
        self._hw_used = ""

        pad = {"padx": 12, "pady": 6}
        f = ttk.Frame(root, padding=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Link (YouTube / Instagram):").grid(row=0, column=0, sticky="w", **pad)
        self.url = ttk.Entry(f, width=60)
        self.url.grid(row=0, column=1, columnspan=2, sticky="we", **pad)

        ttk.Label(f, text="Format / quality:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Combobox(f, textvariable=self.fmt, values=list(FORMATS.keys()),
                     state="readonly", width=46).grid(row=1, column=1, columnspan=2, sticky="we", **pad)

        ttk.Label(f, text="Save to:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.dest, width=44).grid(row=2, column=1, sticky="we", **pad)
        ttk.Button(f, text="Browse...", command=self._choose_folder).grid(row=2, column=2, sticky="e", **pad)

        cwrap = ttk.Frame(f)
        cwrap.grid(row=3, column=0, columnspan=3, sticky="we", padx=12, pady=6)
        ttk.Checkbutton(cwrap, text="Use Chrome login",
                        variable=self.use_cookies,
                        command=self._toggle_profile).pack(side="left")
        ttk.Label(cwrap, text="  profile:").pack(side="left")
        self._profiles = _chrome_profiles()
        values = [p[0] for p in self._profiles] or ["Default"]
        self.profile = tk.StringVar(value=values[0])
        self.cb_profile = ttk.Combobox(cwrap, textvariable=self.profile,
                                       values=values, state="disabled", width=26)
        self.cb_profile.pack(side="left", padx=(4, 0))

        # Cookies from a file. YouTube rotates and invalidates cookies on
        # open tabs, so reading them from a running Chrome is often not
        # enough. A file exported from a private window does not rotate —
        # see COOKIES.md.
        fwrap = ttk.Frame(f)
        fwrap.grid(row=10, column=0, columnspan=3, sticky="we", padx=12, pady=(0, 6))
        ttk.Label(fwrap, text="cookies.txt file (more reliable):").pack(side="left")
        self.cookie_file = tk.StringVar(value="")
        ttk.Entry(fwrap, textvariable=self.cookie_file, width=34).pack(side="left", padx=4)
        ttk.Button(fwrap, text="Browse...", command=self._choose_cookies).pack(side="left")
        ttk.Button(fwrap, text="Clear", command=lambda: self.cookie_file.set("")).pack(side="left", padx=4)

        bwrap = ttk.Frame(f)
        bwrap.grid(row=4, column=0, columnspan=3, pady=(12, 6))
        self.btn = ttk.Button(bwrap, text="Download", command=self._start)
        self.btn.pack(side="left", padx=4)
        ttk.Button(bwrap, text="Open folder", command=self._open_folder).pack(side="left", padx=4)
        self.btn_diag = ttk.Button(bwrap, text="What can be downloaded?",
                                   command=self._start_diagnostics)
        self.btn_diag.pack(side="left", padx=4)

        self.pb = ttk.Progressbar(f, mode="determinate", maximum=100)
        self.pb.grid(row=5, column=0, columnspan=3, sticky="we", **pad)
        ttk.Label(f, textvariable=self.status, foreground="#555").grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        self.cancel_btn = ttk.Button(f, text="✕  Cancel conversion", command=self._cancel_conversion)
        self.cancel_btn.grid(row=7, column=0, columnspan=3, pady=(2, 4))
        self.cancel_btn.grid_remove()  # hidden, shown only while converting

        ttk.Checkbutton(f, text="Re-encode on the GPU (much faster, slightly larger file)",
                        variable=self.use_gpu).grid(row=8, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(f, text="Ensure Adobe Premiere compatibility (re-encode AV1/VP9 to H.264)",
                        variable=self.premiere_compat).grid(row=9, column=0, columnspan=3, sticky="w", **pad)

        f.columnconfigure(1, weight=1)

        # Center the window on screen
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = root.winfo_width()
        h = root.winfo_height()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        # The update check runs in the background — it must not delay
        # startup or crash the app when there is no internet.
        threading.Thread(target=self._check_for_update, daemon=True).start()

    def _check_for_update(self):
        stable, overall = _latest_ytdlp()
        mine = self._ytdlp_version
        # Nightly versions have more than 3 parts
        on_nightly = len(_version_numbers(mine)) > 3

        if stable and _is_newer(mine, stable):
            self._status(f"⚠︎ A newer stable yt-dlp is available "
                         f"({stable}) — run update.command → option 1")
        elif overall and _is_newer(mine, overall):
            where = "option 2" if on_nightly else "option 2 (nightly build)"
            self._status(f"⚠︎ A newer yt-dlp nightly build is available "
                         f"({overall}) — run update.command → {where}")

    def _toggle_profile(self):
        """Choosing a profile only makes sense with cookies switched on."""
        self.cb_profile.config(state="readonly" if self.use_cookies.get() else "disabled")

    def _choose_cookies(self):
        p = filedialog.askopenfilename(
            title="Choose a cookies.txt file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if p:
            self.cookie_file.set(p)

    def _apply_login(self, opts):
        """Add login to opts. A cookies.txt file wins over reading from the
        browser — YouTube rotates and invalidates cookies on open tabs, so
        reading them from a running Chrome often fails even with the right
        account."""
        path = self.cookie_file.get().strip()
        if path and os.path.isfile(path):
            opts["cookiefile"] = path
            return
        if not self.use_cookies.get():
            return
        folder = None
        for label, entry in self._profiles:
            if label == self.profile.get():
                folder = entry
                break
        # Shape: (browser, profile, keyring, container)
        opts["cookiesfrombrowser"] = ("chrome", folder, None, None)

    def _login_label(self):
        path = self.cookie_file.get().strip()
        if path and os.path.isfile(path):
            return f"file {os.path.basename(path)}"
        if self.use_cookies.get():
            return f"Chrome — {self.profile.get()}"
        return "(login off)"

    def _open_folder(self):
        p = self.dest.get()
        if not os.path.isdir(p):
            messagebox.showwarning("Folder not found", f"The folder does not exist:\n{p}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", p])
            elif sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open the folder:\n{e}")

    def _cancel_conversion(self):
        self._cancel_event.set()
        if self._ffmpeg_proc:
            self._ffmpeg_proc.kill()
        self._status("Cancelling conversion...")

    def _show_cancel(self, show):
        def _do():
            if show:
                self.cancel_btn.grid()
            else:
                self.cancel_btn.grid_remove()
        self.root.after(0, _do)

    def _choose_folder(self):
        p = filedialog.askdirectory(initialdir=self.dest.get())
        if p:
            self.dest.set(p)

    def _status(self, t):
        self.root.after(0, lambda: self.status.set(t))

    def _progress(self, v):
        def _do():
            if str(self.pb.cget("mode")) == "indeterminate":
                self.pb.stop()
                self.pb.config(mode="determinate")
            self.pb.config(value=v)
        self.root.after(0, _do)

    def _progress_indeterminate(self, on):
        """Switch the progress bar to 'running' mode when the length is unknown."""
        def _do():
            is_on = str(self.pb.cget("mode")) == "indeterminate"
            if on and not is_on:
                self.pb.config(mode="indeterminate")
                self.pb.start(15)
            elif not on and is_on:
                self.pb.stop()
                self.pb.config(mode="determinate")
        self.root.after(0, _do)

    def _hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                self._progress(d.get("downloaded_bytes", 0) / total * 100)
            self._status("Downloading... " + d.get("_percent_str", "").strip())
        elif d["status"] == "finished":
            self._progress(100)
            self._status("Processing...")

    def _ask_overwrite(self, fname):
        """Show a dialog on the main thread and wait for the answer.
        Returns 'overwrite', 'keep_both' or 'cancel'."""
        result = [None]
        ev = threading.Event()

        def show():
            dlg = tk.Toplevel(self.root)
            dlg.title("File already exists")
            dlg.resizable(False, False)
            dlg.grab_set()

            ttk.Label(
                dlg,
                text=f"A file with the same name\nalready exists in the folder:\n\n{fname}",
                justify="center",
                padding=16,
            ).pack()

            bf = ttk.Frame(dlg, padding=(16, 4, 16, 16))
            bf.pack()

            def pick(v):
                result[0] = v
                dlg.destroy()
                ev.set()

            ttk.Button(bf, text="Overwrite", command=lambda: pick("overwrite")).pack(side="left", padx=5)
            ttk.Button(bf, text="Keep both", command=lambda: pick("keep_both")).pack(side="left", padx=5)
            ttk.Button(bf, text="Cancel",    command=lambda: pick("cancel")).pack(side="left", padx=5)
            dlg.protocol("WM_DELETE_WINDOW", lambda: pick("cancel"))

            # Center on the parent window
            self.root.update_idletasks()
            dlg.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{x}+{y}")

        self.root.after(0, show)
        ev.wait()
        return result[0]

    @staticmethod
    def _unique_path(path):
        """Return the path with (1), (2)... appended if the file exists."""
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        return f"{base} ({i}){ext}"

    def _precheck_file(self, u, opts, p, fmt):
        """Get the video title and check whether the file already exists.
        Returns (rename_suffix, final_override, info, error, overwrite)
        or raises '__CANCELLED__'.

        IMPORTANT: this used to do a full extraction, and the download did
        another one — YouTube got every video twice, which raised the risk
        of being flagged as a bot. Now we extract once (process=False, so no
        format selection) and hand 'info' to the download, which uses it via
        process_ie_result — the same way yt-dlp does for --load-info-json.
        If the extraction fails we return the error, so the same failing
        attempt is not repeated for nothing."""
        try:
            self._status("Getting video information...")
            with yt_dlp.YoutubeDL({**opts, "quiet": True, "no_warnings": True}) as y:
                info = y.extract_info(u, download=False, process=False)
                if not info:
                    return "", None, None, None, False
                raw_path = y.prepare_filename(info)
        except Exception as e:
            return "", None, None, str(e), False

        # Without format selection the extension is still unknown
        # (prepare_filename gives '.NA'), so we compare the base name with
        # the usual output extensions.
        base_no_ext = os.path.splitext(raw_path)[0]
        if fmt in ("RECODE_H264", "RECODE_4K"):
            candidates = [".mp4"]
        elif fmt == "AUDIO_MP3":
            candidates = [".mp3"]
        else:
            candidates = [".mp4", ".webm", ".mkv", ".m4a"]
        expected = next((base_no_ext + k for k in candidates
                         if os.path.exists(base_no_ext + k)), None)

        if not expected:
            return "", None, info, None, False

        choice = self._ask_overwrite(os.path.basename(expected))

        if choice == "cancel":
            raise Exception("__CANCELLED__")
        elif choice == "keep_both":
            unique = self._unique_path(expected)
            unique_base = os.path.splitext(os.path.basename(unique))[0]
            orig_base = os.path.splitext(os.path.basename(expected))[0]
            suffix = unique_base[len(orig_base):]  # e.g. " (1)"
            if fmt in ("RECODE_H264", "RECODE_4K"):
                return suffix, unique, info, None, False
            return suffix, None, info, None, False
        else:
            # Overwrite: by default yt-dlp does NOT overwrite video files
            # (overwrites=None) — it prints "has already been downloaded"
            # and keeps the old file. Without this flag "Overwrite" did
            # nothing for regular downloads.
            return "", None, info, None, True

    def _download(self, u, opts, info=None, info_error=None):
        """Download the video with progressive fallback attempts:
        1. standard attempt (reusing info from the file check, if available)
        2. format selection failed        -> universal selector
        3. YouTube with cookies, error unrelated to login -> without cookies
        4. video unavailable / HTTP 403   -> clients without a PO token,
                                             with a PO token, missing_pot
        """
        def attempt(change=None, without=()):
            o = {**opts, **(change or {})}
            for k in without:
                o.pop(k, None)
            with yt_dlp.YoutubeDL(o) as y:
                return _path_from_info(y.extract_info(u, download=True))

        if info is not None:
            # We already have info from the file check — no extra extraction
            try:
                with yt_dlp.YoutubeDL(opts) as y:
                    return _path_from_info(y.process_ie_result(info, download=True))
            except Exception as e:
                msg = str(e)
        elif info_error and _is_persistent_error(info_error):
            # The file check already hit an error that retrying will not
            # change — repeating it would only load YouTube again. Go straight
            # to the fallback steps. (Network failures never get here.)
            msg = info_error
        else:
            try:
                return attempt()
            except Exception as e:
                msg = str(e)

        # The fallback selector must respect the kind of job. For MP3 it
        # used to be replaced with a video selector, which was plainly wrong.
        is_audio = any(pp.get("key") == "FFmpegExtractAudio"
                       for pp in opts.get("postprocessors", []))
        fallback = "bestaudio*/best" if is_audio else "bestvideo*+bestaudio/best"

        if "Requested format is not available" in msg:
            self._status("Format not available — trying the best available one...")
            try:
                return attempt({"format": fallback})
            except Exception as e2:
                msg = str(e2)

        if not _is_youtube(u):
            raise Exception(msg)

        # Cookies can switch YouTube into SABR mode (Premium accounts
        # especially) or may have been rotated and invalidated — then,
        # paradoxically, trying without them helps. NOT for videos that
        # really need a login, though: there the attempt without cookies
        # would only replace a useful error message.
        has_cookies = "cookiefile" in opts or "cookiesfrombrowser" in opts
        needs_login = ("Please sign in" in msg
                       or "members-only" in msg.lower()
                       or "private video" in msg.lower())
        if has_cookies and not needs_login and not self._cancel_event.is_set():
            self._status("Trying without login (YouTube sometimes blocks cookies)...")
            msg_with_cookies = msg
            try:
                return attempt(without=("cookiefile", "cookiesfrombrowser"))
            except Exception as e_c:
                msg = str(e_c)
                # If it asks for a login without cookies, cookies were the
                # right way — the original error is more useful to the user.
                if "Please sign in" in msg or "Sign in to confirm your age" in msg:
                    msg = msg_with_cookies

        if not _looks_blocked(msg):
            raise Exception(msg)

        # Clients are sent in groups in ONE request — yt-dlp merges formats
        # from all of them. That is one extraction instead of several, and
        # YouTube is less likely to suspect a bot.
        steps = [
            ("clients that need no PO token (tv, web_embedded)",
             {"player_client": _CLIENTS_NO_POT}),
        ]
        if _pot_provider_active():
            steps.append(("PO token clients (mweb, web_safari, android, ios)",
                          {"player_client": _CLIENTS_NEED_POT}))
        # Last resort: also list formats that lack a PO token. Sometimes
        # they work, sometimes they end in 403 — but nothing better is left.
        steps.append(("PO token workaround",
                      {"player_client": _CLIENTS_NO_POT + _CLIENTS_NEED_POT,
                       "formats": ["missing_pot"]}))

        for label, yt_args in steps:
            if self._cancel_event.is_set():
                break
            self._status(f"Video unavailable — trying {label}...")
            try:
                return attempt({"extractor_args": {"youtube": yt_args}})
            except Exception as e3:
                msg = str(e3)

        raise Exception(msg)

    def _start_diagnostics(self):
        """Show what YouTube actually offers for a video. Without this, an
        error like 'Requested format is not available' leaves you guessing
        whether the formats do not exist or we just pick them wrong."""
        u = self.url.get().strip()
        if not u:
            messagebox.showwarning("Error", "Paste a video link first.")
            return
        self.btn_diag.config(state="disabled")
        self._status("Checking available formats...")
        threading.Thread(target=self._diagnostics, args=(u,), daemon=True).start()

    class _LogCollector:
        """Collects yt-dlp output so we can see what happens inside.
        Without it diagnostics are blind — the app suppresses all messages."""
        def __init__(self):
            self.lines = []

        def debug(self, m):
            self.lines.append(m)

        def info(self, m):
            self.lines.append(m)

        def warning(self, m):
            self.lines.append("WARN: " + str(m))

        def error(self, m):
            self.lines.append("ERROR: " + str(m))

    def _diagnostics(self, u):
        # KEY POINT: even extract_info(download=False) does format selection
        # and would fail with the same error as the download — which would
        # make diagnostics pointless. These switches turn that off and also
        # list DRM formats, so it is clear right away whether DRM is the cause.
        log = App._LogCollector()
        opts = {
            "quiet": True, "no_warnings": False, "noplaylist": True,
            "verbose": True, "logger": log,
            "ignore_no_formats_error": True,
            "allow_unplayable_formats": True,
            "extractor_args": {"youtube": {"formats": ["missing_pot"]}},
            "js_runtimes": {k: dict(v) for k, v in _JS_RUNTIMES.items()},
        }
        self._apply_login(opts)
        info = None
        extraction_error = ""
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(u, download=False)
        except Exception as e:
            extraction_error = str(e)

        if info is None:
            # Even when extraction fails, the log may explain why —
            # so we show it instead of a bare error message.
            r = ["Extraction failed.", ""]
            if extraction_error:
                r += [extraction_error[:500], ""]
            r += ["--- Detailed yt-dlp output ---", ""]
            r += self._filter_log(log.lines)
            self._status("Diagnostics failed.")
            self.root.after(0, lambda: self._diagnostics_window("\n".join(r)))
            self.root.after(0, lambda: self.btn_diag.config(state="normal"))
            return

        lines = []
        lines.append(f"PO Token provider:  {_pot_provider_status()}")
        lines.append(f"JS runtime:         {_js_runtime_status()}")
        lines.append(f"Login:              {self._login_label()}")
        lines.append("")
        lines.append(f"Title:   {info.get('title', '?')}")
        if info.get("is_live"):
            lines.append("Status:  ⚠︎ LIVE RIGHT NOW")
        elif info.get("live_status") in ("was_live", "post_live"):
            lines.append(f"Status:  recording of a live stream ({info.get('live_status')})")
        elif info.get("live_status") == "is_upcoming":
            lines.append("Status:  ⚠︎ PREMIERE — the video has not started yet")
        if info.get("duration"):
            d = int(info["duration"])
            lines.append(f"Length:  {d // 60}:{d % 60:02d}")
        lines.append("")

        formats = info.get("formats") or []
        real = [f for f in formats
                if (f.get("vcodec") or "none") != "none"
                or (f.get("acodec") or "none") != "none"]

        whole_log = "\n".join(str(r) for r in log.lines)
        wants_login = ("Please sign in" in whole_log
                       or "Sign in to confirm" in whole_log
                       or "members-only" in whole_log.lower()
                       or "private video" in whole_log.lower())

        if not formats and wants_login:
            # A completely different cause than DRM — and impossible to tell
            # apart without reading the log. That is why it is checked here.
            lines.append("⚠︎ THIS VIDEO REQUIRES A LOGIN")
            lines.append("")
            lines.append("YouTube replied 'Please sign in'.")
            lines.append("The video is private, unlisted, age-restricted")
            lines.append("or for channel members only.")
            lines.append("")
            lines.append("➜ SOLUTION:")
            lines.append("   1. tick 'Use Chrome login'")
            lines.append("   2. next to it pick the PROFILE signed in to Chrome")
            lines.append("      with an account that can watch the video")
            lines.append("   If that does not help, use a cookies.txt file (see COOKIES.md)")
            lines.append("")
            lines.append(f"   Login used now: {self._login_label()}")
            lines.append("")
            lines.append("This is not DRM and not a bug in the app.")
        elif not formats:
            lines.append("NO FORMATS — YouTube returned nothing to download.")
            lines.append("Usually caused by DRM, geo-blocking or members-only content.")
        elif not real:
            lines.append("⚠︎ STORYBOARDS ONLY — no real video or audio.")
            lines.append("")
            lines.append("Formats sb0/sb1/sb2 are just small preview images")
            lines.append("from the timeline, not video.")
            lines.append("")
            lines.append("Cause: YouTube's PO Token / SABR protection.")
            lines.append("Without a valid token yt-dlp gets no video formats.")
            lines.append("This is not DRM and not a bug in the app.")
            lines.append("")
            lines.append("What helps:")
            lines.append("  • run setup-potoken.command (the main fix)")
            lines.append("  • untick 'Use Chrome login'")
            lines.append("  • update.command → option 2 (nightly build)")
            lines.append("")
        else:
            drm = [f for f in formats if f.get("has_drm")]
            usable = [f for f in formats if not f.get("has_drm")]
            lines.append(f"Available formats: {len(formats)}"
                         + (f"   ({len(drm)} of them DRM-protected)" if drm else ""))
            if drm and not usable:
                lines.append("")
                lines.append("⚠︎ ALL formats are DRM-protected — they cannot be downloaded.")
            lines.append("")
            lines.append(f"{'ID':<14}{'RESOLUTION':<13}{'VIDEO':<11}{'AUDIO':<9}{'SIZE':<10}{'DRM'}")
            lines.append("-" * 70)
            for f in formats:
                vc = (f.get("vcodec") or "none").split(".")[0]
                ac = (f.get("acodec") or "none").split(".")[0]
                res = f.get("resolution") or (f"{f.get('height','?')}p" if f.get("height") else "—")
                size = f.get("filesize") or f.get("filesize_approx")
                size = f"{size / 1048576:.0f} MB" if size else "—"
                lines.append(f"{str(f.get('format_id','?')):<14}{res:<13}{vc:<11}{ac:<9}"
                             f"{size:<10}{'YES' if f.get('has_drm') else ''}")

        # Always append the detailed output — when something is wrong it is
        # the only clue
        lines.append("")
        lines.append("=" * 62)
        lines.append("DETAILED yt-dlp OUTPUT")
        lines.append("=" * 62)
        lines.append("")
        lines += self._filter_log(log.lines)

        self._status("Diagnostics done.")
        self.root.after(0, lambda: self._diagnostics_window("\n".join(lines)))
        self.root.after(0, lambda: self.btn_diag.config(state="normal"))

    @staticmethod
    def _filter_log(lines):
        """Pick the lines that actually say something out of dozens.
        The full yt-dlp output is too long and mostly noise."""
        keywords = ("pot", "token", "sabr", "format", "client", "player",
                    "WARN", "ERROR", "skip", "nsig", "sign", "cookie",
                    "Extracting", "unavailable", "403", "429")
        picked = [r for r in lines
                  if any(k.lower() in str(r).lower() for k in keywords)]
        if not picked:
            picked = lines[-40:]
        return [str(r)[:200] for r in picked[-60:]]

    def _diagnostics_window(self, text):
        dlg = tk.Toplevel(self.root)
        dlg.title("What can be downloaded for this video")
        dlg.geometry("720x480")
        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(frame)
        sb.pack(side="right", fill="y")
        txt = tk.Text(frame, wrap="none", yscrollcommand=sb.set,
                      font=("Menlo", 11), borderwidth=0)
        txt.pack(fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        x = self.root.winfo_x() + (self.root.winfo_width() - 720) // 2
        y = self.root.winfo_y() + 40
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _start(self):
        u = self.url.get().strip()
        if not u:
            messagebox.showwarning("Error", "Paste a video link first.")
            return
        self.btn.config(state="disabled")
        self.pb.config(value=0)
        self._status("Starting...")
        threading.Thread(target=self._download_job, args=(u,), daemon=True).start()

    def _download_job(self, u):
        p = self.dest.get()
        os.makedirs(p, exist_ok=True)
        fmt = FORMATS[self.fmt.get()]
        is_yt = _is_youtube(u)

        try:
            opts = {
                "outtmpl": os.path.join(p, "%(title)s.%(ext)s"),
                "progress_hooks": [self._hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "js_runtimes": {k: dict(v) for k, v in _JS_RUNTIMES.items()},
                # Throttling protection: YouTube often drops the speed to a
                # fraction after a while. Below 100 KB/s yt-dlp re-extracts
                # fresh URLs; downloading in 10 MB chunks avoids throttling
                # altogether.
                "throttledratelimit": 100 * 1024,
                "http_chunk_size": 10 * 1024 * 1024,
                # Live stream recordings and long videos come in fragments —
                # 4 at once instead of one cuts the time considerably.
                "concurrent_fragment_downloads": 4,
            }
            if FFMPEG_DIR:
                opts["ffmpeg_location"] = FFMPEG_DIR
            self._apply_login(opts)
            if is_yt:
                # YouTube serves live streams and premieres via an HLS/DASH
                # manifest. Without this only the part from "now" is
                # downloaded, or it fails with "Requested format is not
                # available". Has no effect on regular videos.
                opts["live_from_start"] = True
            # NOTE: player_client is intentionally NOT set. yt-dlp picks the
            # client itself and its defaults are tuned continuously to
            # YouTube's changes. Hardcoding caused "The page needs to be
            # reloaded" (web / web_safari clients combined with cookies).

            # CAREFUL: the bare "best" selector means "the best format with
            # video AND audio in ONE file" in yt-dlp. YouTube no longer
            # offers those for most videos (video and audio are separate),
            # so "best" causes "Requested format is not available" there.
            if fmt == "AUTO":
                opts["format"] = "bestvideo*+bestaudio/best"
                opts["merge_output_format"] = "mp4"
            elif fmt == "AUDIO_MP3":
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                           "preferredcodec": "mp3",
                                           "preferredquality": "192"}]
            elif fmt in ("RECODE_H264", "RECODE_4K"):
                # bestvideo* (with the star) also accepts merged formats,
                # not just pure video streams — otherwise it fails on videos
                # without a separate video stream.
                opts["format"] = ("bestvideo*[height<=2160]+bestaudio/best[height<=2160]/best"
                                  if fmt == "RECODE_4K" else "bestvideo*+bestaudio/best")
            else:
                opts["format"] = fmt if is_yt else "bestvideo*+bestaudio/best"
                opts["merge_output_format"] = "mp4"

            # File check — also the single extraction of the video, whose
            # result is reused for the download
            rename_suffix, final_override, info, info_error, overwrite = \
                self._precheck_file(u, opts, p, fmt)
            if rename_suffix:
                opts["outtmpl"] = os.path.join(p, f"%(title)s{rename_suffix}.%(ext)s")
            if overwrite:
                opts["overwrites"] = True

            if fmt in ("RECODE_H264", "RECODE_4K"):
                self._download_and_recode(u, p, fmt, opts, final_override, info, info_error)
            else:
                path = self._download(u, opts, info, info_error)
                if fmt != "AUDIO_MP3" and self.premiere_compat.get():
                    self._ensure_premiere_compat(path)

            if self._hw_used == "CPU" and self._gpu_fail_reason:
                self._status(f"Done (CPU). GPU failed: {self._gpu_fail_reason}")
            elif self._hw_used:
                self._status(f"Done! File saved.  (encoded on {self._hw_used})")
            else:
                self._status("Done! File saved.")
        except Exception as e:
            if str(e) == "__CANCELLED__":
                self._status("Cancelled. The unfinished file was deleted.")
                return
            self._status("Download failed.")
            m = str(e)
            if "DRM" in m:
                m = (
                    "This video is DRM-protected.\n\n"
                    "YouTube encrypts it on purpose — typical for films,\n"
                    "TV series, rentals and licensed music.\n\n"
                    "Such a video cannot be downloaded, not even with a login.\n"
                    "This is not a bug in the app."
                )
            elif "needs to be reloaded" in m:
                m = (
                    "YouTube rejected the request.\n\n"
                    "Most common cause: Chrome cookies are switched on.\n"
                    "Try UNTICKING 'Use Chrome login'.\n\n"
                    "If that does not help, run update.command —\n"
                    "this error gets fixed on the yt-dlp side.\n\n"
                    f"Original error:\n{m}"
                )
            elif "Please sign in" in m or "Sign in to confirm" in m:
                m = (
                    "This video requires a login.\n\n"
                    f"Used now: {self._login_label()}\n\n"
                    "If you already tried a Chrome profile and it did not help,\n"
                    "that is a known issue — YouTube keeps rotating cookies\n"
                    "on open tabs, which invalidates them.\n\n"
                    "➜ SOLUTION: use a cookies.txt file\n"
                    "   The exact steps are in COOKIES.md\n"
                    "   in the app folder."
                )
            elif "Requested format is not available" in m:
                m = (
                    "No usable format was found for this video.\n\n"
                    "➜ Click 'What can be downloaded?' — it lists\n"
                    "   what YouTube really offers for this video.\n"
                    "   That shows whether there are no formats at all,\n"
                    "   or just none matching the chosen quality.\n\n"
                    "If the list is empty, it is DRM, geo-blocking\n"
                    "or PO Token protection — nothing can be done.\n\n"
                    f"Original error:\n{m}"
                )
            elif "not available" in m or "Sign in to confirm" in m or "unable to extract" in m.lower():
                m = (
                    "YouTube did not provide this video.\n\n"
                    "The app has already tried alternative ways\n"
                    "(TV and embedded players, without cookies,\n"
                    "PO token workaround) — without success.\n\n"
                    "This usually means one of:\n"
                    "• the video is blocked in your country\n"
                    "• it is age-restricted (try 'Use Chrome login')\n"
                    "• it is for channel members only, or private\n"
                    "• YouTube requires a PO Token that yt-dlp does not have\n\n"
                    f"Original error:\n{m}"
                )
            elif "Unsupported URL" in m:
                m = (
                    "This URL is not supported.\n\n"
                    "For private content try ticking\n"
                    "'Use Chrome login'.\n\n"
                    f"Original error:\n{m}"
                )
            self.root.after(0, lambda: messagebox.showerror("Error", m))
        finally:
            self.root.after(0, lambda: self.btn.config(state="normal"))

    def _download_and_recode(self, u, p, fmt, opts, final_override=None, info=None, info_error=None):
        marker = f"YTTEMP{int(time.time())}"
        dl_opts = {**opts}
        dl_opts["outtmpl"] = os.path.join(p, f"%(title)s [{marker}].%(ext)s")
        dl_opts["merge_output_format"] = "mkv"

        # Download — the same fallback attempts as the regular path
        downloaded = self._download(u, dl_opts, info, info_error)

        # Temporary file: prefer the path returned by yt-dlp; searching the
        # folder for the marker is only a backup
        if downloaded and os.path.exists(downloaded):
            temp_file = downloaded
        else:
            temp_files = [os.path.join(p, f) for f in os.listdir(p) if f"[{marker}]" in f]
            if not temp_files:
                raise Exception("Could not find the temporary file after downloading.")
            temp_file = max(temp_files, key=os.path.getmtime)

        # Decide the output file
        if final_override:
            final_file = final_override
        else:
            out_base = os.path.basename(temp_file).replace(f" [{marker}]", "").rsplit(".", 1)[0]
            final_file = os.path.join(p, out_base + ".mp4")

        self._transcode(temp_file, final_file)

    def _ensure_premiere_compat(self, path):
        """If the downloaded video uses a codec Premiere cannot read (AV1,
        VP9), re-encode it to H.264. If it already is H.264, do nothing —
        a needless re-encode would only lower quality and waste time."""
        if not path or not os.path.exists(path):
            return
        ffprobe_bin = os.path.join(FFMPEG_DIR, "ffprobe") if FFMPEG_DIR else "ffprobe"
        self._status("Checking the codec...")
        codec = _video_codec(ffprobe_bin, path)
        if not codec or not any(k in codec for k in _INCOMPATIBLE_CODECS):
            return  # already compatible (h264), or cannot be detected

        base, ext = os.path.splitext(path)
        temp = base + " [CONVERTING].tmp" + ext
        target = base + ".mp4"
        try:
            os.replace(path, temp)
        except Exception:
            return  # if it cannot be renamed, better keep the original file

        self._status(f"The video is {codec.upper()} — re-encoding for Premiere...")
        try:
            self._transcode(temp, target)
        except Exception:
            # On failure put the original file back, so nothing is lost
            try:
                if os.path.exists(temp) and not os.path.exists(path):
                    os.replace(temp, path)
            except Exception:
                pass
            raise

    def _transcode(self, source, target):
        """Re-encode a file to H.264/AAC in MP4. Tries the GPU first, then
        the CPU. The source file is deleted only after success."""
        ffmpeg_bin = os.path.join(FFMPEG_DIR, "ffmpeg") if FFMPEG_DIR else "ffmpeg"
        ffprobe_bin = os.path.join(FFMPEG_DIR, "ffprobe") if FFMPEG_DIR else "ffprobe"

        # Duration for progress, height for picking the bitrate
        duration = None
        height = 1080
        try:
            data = json.loads(subprocess.run(
                [ffprobe_bin, "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", source],
                capture_output=True, text=True,
            ).stdout)
            duration = float(data["format"]["duration"])
            for s in data.get("streams", []):
                if s.get("codec_type") == "video" and s.get("height"):
                    height = int(s["height"])
                    break
        except Exception:
            pass

        def _build_cmd(encoder, hw_decode):
            """Build the ffmpeg command. encoder='' means CPU (libx264).
            hw_decode controls hardware DECODING separately from encoding —
            they are independent and one can fail without the other."""
            hwdec = []
            if encoder:
                br, maxbr = _bitrate_for_height(height)
                vid = ["-c:v", encoder, "-b:v", br, "-maxrate", maxbr,
                       "-bufsize", maxbr, "-profile:v", "high"]
                if encoder == "h264_videotoolbox":
                    # allow_sw=0 FORCES hardware encoding. With 1 VideoToolbox
                    # would silently fall back to software and run at CPU speed.
                    vid += ["-allow_sw", "0"]
                    if hw_decode:
                        hwdec = ["-hwaccel", "videotoolbox"]
                elif encoder == "h264_nvenc":
                    vid += ["-preset", "p5", "-rc", "vbr"]
                    if hw_decode:
                        hwdec = ["-hwaccel", "cuda"]
                elif encoder == "h264_qsv":
                    if hw_decode:
                        hwdec = ["-hwaccel", "qsv"]
            else:
                vid = ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]
            return [
                ffmpeg_bin, *hwdec, "-i", source,
                *vid,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-nostats",
                "-y", target,
            ]

        gpu_enc = _gpu_encoder(ffmpeg_bin) if self.use_gpu.get() else ""
        # Order of attempts. Hardware DECODING and hardware ENCODING are
        # independent — e.g. only M3 and newer decode AV1 in hardware, while
        # the H.264 encoder works on M1 too.
        if gpu_enc:
            attempts = [
                (gpu_enc, True,  "GPU"),
                (gpu_enc, False, "GPU"),
                ("",      False, "CPU"),
            ]
        else:
            attempts = [("", False, "CPU")]

        self._cancel_event.clear()
        last_error = ""
        self._gpu_fail_reason = ""
        self._hw_used = ""

        for i, (enc, hw_decode, where) in enumerate(attempts):
            self._encoder_used = enc or "libx264"
            if i == 0:
                self._status(f"Re-encoding to H.264 ({where})...")
            elif enc:
                self._status("Hardware decoding failed — the GPU keeps encoding...")
            else:
                self._status("GPU encoding failed — trying the CPU...")
            self._show_cancel(True)
            self._progress(0)

            proc = subprocess.Popen(_build_cmd(enc, hw_decode), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            self._ffmpeg_proc = proc

            # stderr is read in a separate thread, otherwise a full buffer
            # would block and the process would never finish
            err = []
            threading.Thread(
                target=lambda p=proc, e=err: [e.append(l) for l in p.stderr],
                daemon=True).start()

            cancelled = False
            speed = None
            for line in proc.stdout:
                if self._cancel_event.is_set():
                    proc.kill()
                    cancelled = True
                    break
                cur, spd = _parse_progress(line)
                if spd is not None:
                    speed = spd
                if cur is None:
                    continue
                if duration:
                    pct = min(cur / duration * 100, 99)
                    rem = max(duration - cur, 0)
                    if speed and speed > 0:
                        rem = rem / speed
                    self._progress(pct)
                    self._status(f"Re-encoding to H.264 ({where})... {pct:.0f}%  "
                                 f"(~{int(rem // 60)}:{int(rem % 60):02d} left)")
                else:
                    # Unknown length (e.g. a live stream recording).
                    # Without this the UI would look frozen.
                    self._progress_indeterminate(True)
                    s = (f"Re-encoding to H.264 ({where})... processed "
                         f"{int(cur // 60)}:{int(cur % 60):02d}")
                    if speed:
                        s += f"  ({speed:.1f}× speed)"
                    self._status(s)

            proc.wait()
            self._ffmpeg_proc = None
            self._show_cancel(False)
            self._progress_indeterminate(False)

            if cancelled or self._cancel_event.is_set():
                self._status("Cancelling and cleaning up...")
                time.sleep(0.3)  # give the OS a moment to release the file
                for f in (target, source):
                    try:
                        if os.path.exists(f):
                            os.remove(f)
                    except Exception:
                        pass
                raise Exception("__CANCELLED__")

            if proc.returncode == 0:
                # Only now is it safe to delete the source
                try:
                    if os.path.abspath(source) != os.path.abspath(target):
                        os.remove(source)
                except Exception:
                    pass
                self._hw_used = where
                self._progress(100)
                return

            last_error = "".join(err)
            # Remember why the GPU failed — otherwise the reason would be lost
            # and the user would only see "it ran on the CPU" with no explanation.
            if enc and not self._gpu_fail_reason:
                self._gpu_fail_reason = _error_gist(last_error)

        raise Exception("ffmpeg error during conversion:\n" + last_error[-800:])


if __name__ == "__main__":
    r = tk.Tk()
    App(r)
    r.mainloop()
