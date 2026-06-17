#!/usr/bin/env python3
# =============================================================================
#  Centralized Examination Operations Platform
#  Akshay Singh | iTest Content Team | SIFY Technologies
# =============================================================================
import os, sys, time, subprocess, threading, webbrowser, hashlib, json
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, messagebox as msg

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
PYTHON    = sys.executable

# ── VCS DEPLOYMENT METADATA ──────────────────────────────────────────────────
CURRENT_VERSION   = "2.0.0"
# Replace these URLs with your real remote GitHub file locations
VERSION_CHECK_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/version.json"
APPROVED_KEYS_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/whitelist.json"

TOOLS = [
    {
        "id":     "cctv",
        "title":  "CCTV Audit Tool",
        "sub":    "Examination Compliance Auditing",
        "desc":   "YOLO + Gemini AI analysis of CCTV footage. Dual-ROI OCR, compliance monitoring and automated PDF audit reports.",
        "icon":   "\U0001f3a5",
        "type":   "streamlit",
        "color":  "#1565C0",
        "light":  "#E3F2FD",
        "dark":   "#0D47A1",
        "tag":    "Streamlit  \u00b7  Ports 8501 / 8503",
        "label":  "AI  \u00b7  VISION",
        "instances": [
            {
                "id":     "cctv1",
                "name":   "1",
                "type":   "streamlit",
                "script": os.path.join(TOOLS_DIR, "cctv_analyser_1.py"),
                "port":   8501,
                "url":    "http://localhost:8501",
            },
            {
                "id":     "cctv2",
                "name":   "2",
                "type":   "streamlit",
                "script": os.path.join(TOOLS_DIR, "cctv_analyser_2.py"),
                "port":   8503,
                "url":    "http://localhost:8503",
            },
        ],
    },
    {
        "id":     "cbt",
        "title":  "CBT Reconciliation",
        "sub":    "Attendance Cross-Verification Tool",
        "desc":   "Gemini AI PDF extraction. Biometric vs Attendance cross-match with colour-coded Excel report output.",
        "icon":   "\U0001f4cb",
        "type":   "streamlit",
        "script": os.path.join(TOOLS_DIR, "cbt_reconciliation.py"),
        "port":   8502,
        "url":    "http://localhost:8502",
        "color":  "#00838F",
        "light":  "#E0F7FA",
        "dark":   "#006064",
        "tag":    "Streamlit  \u00b7  Port 8502",
        "label":  "AI  \u00b7  REPORTS",
    },
    {
        "id":     "dav",
        "title":  "DAV \u2192 MP4 Converter",
        "sub":    "CCTV Recording Format Conversion",
        "desc":   "Batch convert Hikvision / Dahua .dav recordings to MP4. Auto-retry with re-encode fallback via ffmpeg.",
        "icon":   "\u2194",
        "type":   "tkinter",
        "script": os.path.join(TOOLS_DIR, "dav_converter.py"),
        "port":   None,
        "url":    None,
        "color":  "#37474F",
        "light":  "#ECEFF1",
        "dark":   "#212B30",
        "tag":    "Desktop App  \u00b7  Tkinter",
        "label":  "CONVERT",
    },
    {
        "id":     "merger",
        "title":  "MP4 Merger",
        "sub":    "Segmented Footage Concatenation",
        "desc":   "Merge timestamp-segmented MP4 files by camera prefix using ffmpeg concat. Folder picker with live log output.",
        "icon":   "\u25b6",
        "type":   "tkinter",
        "script": os.path.join(TOOLS_DIR, "mp4_merger.py"),
        "port":   None,
        "url":    None,
        "color":  "#3949AB",
        "light":  "#E8EAF6",
        "dark":   "#1A237E",
        "tag":    "Desktop App  \u00b7  Tkinter",
        "label":  "MERGE",
    },
    {
        "id":     "losslesscut",
        "title":  "LosslessCut Editor",
        "sub":    "Lossless Video Trimming & Segment Extraction",
        "desc":   "Frame-accurate video trimming and segment extraction without re-encoding. Fast processing, quality preservation, and clip generation for CCTV footage review.",
        "icon":   "\u2702",
        "type":   "exe",
        "script": os.path.join(TOOLS_DIR, "LosslessCut-win-x64", "LosslessCut.exe"),
        "port":   None,
        "url":    None,
        "color":  "#546E7A",
        "light":  "#ECEFF1",
        "dark":   "#37474F",
        "tag":    "Desktop App  \u00b7  Offline",
        "label":  "TRIM",
    },
]

# ── Palette (white theme) ─────────────────────────────────────────────────────
BG       = "#F0F2F8"
WHITE    = "#FFFFFF"
PANEL    = "#FFFFFF"
CARD     = "#FFFFFF"
BORD     = "#E0E4EF"
BORD2    = "#C8CDE0"
TEXT     = "#1A1F3A"
TEXT2    = "#4A5080"
MUTED    = "#8890B0"
DIM      = "#B0B8D0"
ACCENT   = "#1F4E79"
RED_A    = "#C62828"
GREEN_A  = "#2E7D32"
AMBER_A  = "#F57F17"
ERR_A    = "#C62828"
GREY_ST  = "#78909C"
SIFY_BLU = "#003087"
SIFY_RED = "#E31837"

procs  = {}

def _all_units():
    units = []
    for t in TOOLS:
        if "instances" in t:
            for inst in t["instances"]:
                units.append(inst)
        else:
            units.append(t)
    return units

def _find_tool_for_id(tid):
    for t in TOOLS:
        if t["id"] == tid:
            return t
        if "instances" in t:
            for inst in t["instances"]:
                if inst["id"] == tid:
                    return t
    return None

states = {u["id"]: "idle" for u in _all_units()}

# ── HWID Security Core ────────────────────────────────────────────────────────
def get_hardware_id():
    """Generates an explicit unique internal cryptographic hardware ID hash."""
    try:
        cmd_cpu = "wmic cpu get processorid"
        cmd_base = "wmic baseboard get serialnumber"
        cpu = subprocess.check_output(cmd_cpu, shell=True).decode().split('\n')[1].strip()
        base = subprocess.check_output(cmd_base, shell=True).decode().split('\n')[1].strip()
        combined = f"{cpu}::{base}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24].upper()
    except:
        # Emergency hardware signature tracking fallback
        fallback = os.environ.get('COMPUTERNAME', 'GENERIC_HOST_NODE')
        return hashlib.sha256(fallback.encode()).hexdigest()[:24].upper()

def is_locally_activated():
    """Check if the system registration token exists locally."""
    lic_file = os.path.join(BASE_DIR, "license.key")
    if not os.path.exists(lic_file):
        return False
    try:
        with open(lic_file, "r") as f:
            stored_key = f.read().strip()
        return stored_key == get_hardware_id()
    except:
        return False

# ── Process control ───────────────────────────────────────────────────────────
def _launch(tool, cb):
    tid = tool["id"]
    p = procs.get(tid)
    if p and p.poll() is None:
        p.terminate(); time.sleep(0.4)
    states[tid] = "starting"; cb(tid, "starting")
    try:
        if tool["type"] == "streamlit":
            cmd = [PYTHON, "-m", "streamlit", "run", tool["script"],
                   "--server.port", str(tool["port"]),
                   "--server.headless", "true",
                   "--browser.gatherUsageStats", "false"]
        elif tool["type"] == "exe":
            cmd = ["explorer", tool["script"]]
        else:
            cmd = [PYTHON, tool["script"]]
        popen_kwargs = dict(stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
        if tool["type"] == "exe":
            popen_kwargs["cwd"] = os.path.dirname(tool["script"])
        proc = subprocess.Popen(cmd, **popen_kwargs)
        procs[tid] = proc
        states[tid] = "running"; cb(tid, "running")
        if tool["url"]:
            time.sleep(3.0); webbrowser.open(tool["url"])
        proc.wait()
        states[tid] = "stopped"; cb(tid, "stopped")
    except Exception:
        states[tid] = "error"; cb(tid, "error")

def launch_tool(tool, cb):
    threading.Thread(target=_launch, args=(tool, cb), daemon=True).start()

def stop_tool(tool, cb):
    tid = tool["id"]
    p = procs.get(tid)
    if p and p.poll() is None:
        p.terminate()
    states[tid] = "stopped"; cb(tid, "stopped")

def launch_all(cb):
    for u in _all_units():
        time.sleep(0.3); launch_tool(u, cb)

def stop_all(cb):
    for u in _all_units():
        stop_tool(u, cb)

def paint_h(canvas, w, h, c1, c2):
    def _hx(h):
        h = h.lstrip("#")
        return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    r1,g1,b1 = _hx(c1); r2,g2,b2 = _hx(c2)
    for i in range(max(w,1)):
        t = i/(max(w,1)-1) if w>1 else 0
        r=int(r1+(r2-r1)*t); g=int(g1+(g2-g1)*t); b=int(b1+(b2-b1)*t)
        canvas.create_line(i,0,i,h, fill=f"#{r:02x}{g:02x}{b:02x}")

_LOGO_PATH = os.path.join(BASE_DIR, "sify-logo.png")
def load_sify_logo():
    try:
        from PIL import Image, ImageTk
        img = Image.open(_LOGO_PATH)
        target_h = 48
        ratio = target_h / img.height
        img = img.resize((int(img.width * ratio), target_h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except:
        try:
            ph = tk.PhotoImage(file=_LOGO_PATH)
            factor = max(1, ph.height() // 48)
            if factor > 1: ph = ph.subsample(factor, factor)
            return ph
        except: return None

# ── Main UI Window Entry ──────────────────────────────────────────────────────
class Hub:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Centralized Examination Operations Platform (v{CURRENT_VERSION})")
        self.root.configure(bg=BG)
        self.root.geometry("1280x900")
        self.root.minsize(1100, 800)

        self._dots  = {}; self._slbls = {}; self._lbtns = {}
        self._sbtns = {}; self._pjobs = {}

        if not is_locally_activated():
            self._render_lockout_screen()
        else:
            self._render_main_application()

    def _render_lockout_screen(self):
        """Displays security registration lock interface."""
        for widget in self.root.winfo_children():
            widget.destroy()

        lock_frame = tk.Frame(self.root, bg=WHITE, highlightthickness=1, highlightbackground=BORD2)
        lock_frame.place(relx=0.5, rely=0.5, anchor="center", width=550, height=450)

        tk.Label(lock_frame, text="\U0001f512 Activation Required", font=("Segoe UI", 18, "bold"), bg=WHITE, fg=SIFY_BLU).pack(pady=(40, 10))
        tk.Label(lock_frame, text="This platform node requires administrator access confirmation.", font=("Segoe UI", 10), bg=WHITE, fg=TEXT2).pack()

        hwid_container = tk.Frame(lock_frame, bg=BG, padx=15, pady=15)
        hwid_container.pack(pady=30, fill="x", padx=40)

        tk.Label(hwid_container, text="YOUR HARDWARE REGISTRATION ID:", font=("Segoe UI", 8, "bold"), bg=BG, fg=MUTED).pack(anchor="w")
        
        self.hwid_var = tk.StringVar(value=get_hardware_id())
        hwid_entry = tk.Entry(hwid_container, textvariable=self.hwid_var, font=("Consolas", 12, "bold"), bd=0, bg=BG, fg=TEXT, justify="center", state="readonly")
        hwid_entry.pack(fill="x", pady=(5, 5))

        tk.Button(hwid_container, text="Copy ID to Clipboard", font=("Segoe UI", 9), bg=WHITE, fg=ACCENT, relief="groove", command=self._copy_hwid).pack(pady=(5, 0))

        btn_row = tk.Frame(lock_frame, bg=WHITE)
        btn_row.pack(fill="x", padx=40, pady=10)

        tk.Button(btn_row, text="Request Activation Online", font=("Segoe UI", 10, "bold"), bg=SIFY_BLU, fg=WHITE, relief="flat", pady=8, command=self._request_verification_payload).pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Button(btn_row, text="Verify Access Status", font=("Segoe UI", 10, "bold"), bg=GREEN_A, fg=WHITE, relief="flat", pady=8, command=self._check_activation_clearance).pack(side="right", fill="x", expand=True)

    def _copy_hwid(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.hwid_var.get())
        msg.showinfo("Success", "Hardware ID copied to clipboard.")

    def _request_verification_payload(self):
        """Launches messaging endpoint passing registration parameters."""
        webbrowser.open(f"https://github.com/YOUR_USERNAME/YOUR_REPO/issues/new?title=Activation+Request+{get_hardware_id()}")

    def _check_activation_clearance(self):
        """Queries remote database whitelist array to verify system validation."""
        import requests
        try:
            res = requests.get(APPROVED_KEYS_URL, timeout=8)
            if res.status_code == 200:
                whitelist = res.json().get("allowed_hwids", [])
                if get_hardware_id() in whitelist:
                    with open(os.path.join(BASE_DIR, "license.key"), "w") as f:
                        f.write(get_hardware_id())
                    msg.showinfo("Cleared", "Device authenticated successfully! Launching app...")
                    self._render_main_application()
                else:
                    msg.showerror("Denied", "Device registration reference not located on server asset index.")
            else:
                msg.showerror("Network Issue", "Server endpoint error encountered.")
        except Exception as e:
            msg.showerror("Error", f"Failed to connect to validation servers: {str(e)}")

    def _render_main_application(self):
        """Renders primary operational application workspace panels."""
        for widget in self.root.winfo_children():
            widget.destroy()

        self._header()
        self._stats_bar()
        self._body()
        self._footer()
        self._poll()
        
        # Spawn asynchronous version synchronization threads
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _check_for_updates(self):
        """Asynchronously queries GitHub version control maps."""
        import requests
        try:
            response = requests.get(VERSION_CHECK_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                remote_version = data.get("version", "2.0.0")
                if remote_version != CURRENT_VERSION:
                    self.root.after(0, lambda: self._prompt_update(data))
        except:
            pass

    def _prompt_update(self, update_metadata):
        if msg.askyesno("Update Available", f"A new framework release (v{update_metadata['version']}) is ready.\n\nDescription: {update_metadata.get('changelog', 'Bug fixes and performance upgrades')}\n\nDo you want to apply updates automatically?"):
            self._execute_platform_migration(update_metadata.get("download_url"))

    def _execute_platform_migration(self, package_url):
        """Downloads package update and structures runtime pipeline substitution."""
        import requests, zipfile
        updater_window = tk.Toplevel(self.root)
        updater_window.title("System Migration Suite")
        updater_window.geometry("400x150")
        updater_window.configure(bg=WHITE)
        updater_window.transient(self.root)
        updater_window.grab_set()

        lbl = tk.Label(updater_window, text="Downloading framework update packages...", font=("Segoe UI", 10), bg=WHITE, fg=TEXT)
        lbl.pack(pady=40)

        def run_download():
            try:
                target_zip = os.path.join(BASE_DIR, "update_payload.zip")
                r = requests.get(package_url, stream=True)
                with open(target_zip, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                
                lbl.config(text="Extracting binaries and cleaning cache...")
                with zipfile.ZipFile(target_zip, 'r') as zip_ref:
                    # Overwrite existing files securely
                    zip_ref.extractall(BASE_DIR)
                
                os.remove(target_zip)
                msg.showinfo("Completed", "Migration finished. App will restart now.")
                self.root.after(0, lambda: sys.exit(999)) # Special exit code handled by our .bat file to reload loop
            except Exception as e:
                msg.showerror("Migration Error", f"Failed to unpack delta patches automatically: {str(e)}")
                updater_window.destroy()

        threading.Thread(target=run_download, daemon=True).start()

    # ── Header ────────────────────────────────────────────────────────────────
    def _header(self):
        bar = tk.Canvas(self.root, height=5, bg=PANEL, highlightthickness=0)
        bar.pack(fill="x")
        bar.bind("<Configure>", lambda e: paint_h(e.widget, e.width, 5, SIFY_BLU, SIFY_RED))

        hdr = tk.Frame(self.root, bg=PANEL, pady=14)
        hdr.pack(fill="x")

        left = tk.Frame(hdr, bg=PANEL)
        left.pack(side="left", padx=32)

        logo_row = tk.Frame(left, bg=PANEL)
        logo_row.pack(anchor="w")

        self._logo_img = load_sify_logo()
        if self._logo_img is not None:
            sify = tk.Label(logo_row, image=self._logo_img, bg=PANEL)
        else:
            sify = tk.Label(logo_row, text="SIFY", font=("Segoe UI", 13, "bold"), bg=PANEL, fg=SIFY_BLU)
        sify.pack(side="left", padx=(0, 14))

        title_block = tk.Frame(logo_row, bg=PANEL)
        title_block.pack(side="left")

        tk.Label(title_block, text="Centralized Examination Operations Platform", font=("Segoe UI", 17, "bold"), bg=PANEL, fg=TEXT).pack(anchor="w")
        tk.Label(title_block, text=f"Akshay Singh  \u00b7  iTest Content Team  \u00b7  SIFY Technologies  \u00b7  v{CURRENT_VERSION}", font=("Segoe UI", 9), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(hdr, bg=PANEL)
        right.pack(side="right", padx=32)

        tk.Button(right, text="\u25b6\u25b6  Launch All", font=("Segoe UI", 10, "bold"), bg=GREEN_A, fg=WHITE, relief="flat", padx=20, pady=9, cursor="hand2", bd=0, activebackground="#1B5E20", activeforeground=WHITE, command=lambda: launch_all(self._cb)).pack(side="left", padx=(0, 10))
        tk.Button(right, text="\u25a0  Stop All", font=("Segoe UI", 10, "bold"), bg="#455A64", fg=WHITE, relief="flat", padx=20, pady=9, cursor="hand2", bd=0, activebackground="#263238", activeforeground=WHITE, command=lambda: stop_all(self._cb)).pack(side="left")
        tk.Frame(self.root, bg=BORD, height=1).pack(fill="x")

    def _stats_bar(self):
        bar = tk.Frame(self.root, bg=ACCENT, height=10)
        bar.pack(fill="x")

    # ── Body ──────────────────────────────────────────────────────────────────
    def _body(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=30, pady=22)

        sh = tk.Frame(outer, bg=BG)
        sh.pack(fill="x", pady=(0, 16))
        tk.Label(sh, text="EXAMINATION TOOLS", font=("Segoe UI", 9, "bold"), bg=BG, fg=MUTED).pack(side="left")
        tk.Label(sh, text="Click \u25b6 Launch to start any tool independently", font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(side="right")

        grid = tk.Frame(outer, bg=BG)
        grid.pack(fill="both", expand=True)
        for i in range(6): grid.columnconfigure(i, weight=1, uniform="col")
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

        row1 = TOOLS[:3]
        row2 = TOOLS[3:]

        for i, t in enumerate(row1): self._card(grid, t, row=0, col=i * 2, colspan=2)
        n2 = len(row2)
        offsets = [1, 3] if n2 == 2 else ([2] if n2 == 1 else [i * (6 // max(n2, 1)) for i in range(n2)])
        for i, t in enumerate(row2): self._card(grid, t, row=1, col=offsets[i], colspan=2)

    # ── Single card ───────────────────────────────────────────────────────────
    def _card(self, parent, tool, row, col, colspan=1):
        tid = tool["id"]
        outer = tk.Frame(parent, bg=BG, padx=6, pady=4)
        outer.grid(row=row, column=col, columnspan=colspan, sticky="nsew")

        card = tk.Frame(outer, bg=CARD, highlightthickness=1, highlightbackground=BORD2)
        card.pack(fill="both", expand=True)

        band = tk.Frame(card, bg=tool["color"], pady=16)
        band.pack(fill="x")

        band_inner = tk.Frame(band, bg=tool["color"])
        band_inner.pack(padx=20)

        icon_frame = tk.Frame(band_inner, bg=WHITE, width=52, height=52)
        icon_frame.pack(side="left")
        icon_frame.pack_propagate(False)
        tk.Label(icon_frame, text=tool["icon"], font=("Segoe UI Emoji", 22), bg=WHITE, fg=tool["color"]).place(relx=0.5, rely=0.5, anchor="center")

        title_area = tk.Frame(band_inner, bg=tool["color"])
        title_area.pack(side="left", padx=(14, 0))

        tk.Label(title_area, text=tool["title"], font=("Segoe UI", 13, "bold"), bg=tool["color"], fg=WHITE, anchor="w").pack(anchor="w")
        tk.Label(title_area, text=tool["sub"], font=("Segoe UI", 8), bg=tool["color"], fg=tool["light"], anchor="w").pack(anchor="w", pady=(2, 0))

        status_strip = tk.Frame(card, bg=tool["light"], pady=5)
        status_strip.pack(fill="x")
        ss_inner = tk.Frame(status_strip, bg=tool["light"])
        ss_inner.pack(padx=20, fill="x")

        if "instances" in tool:
            for idx, inst in enumerate(tool["instances"]):
                iid = inst["id"]
                grp = tk.Frame(ss_inner, bg=tool["light"])
                grp.pack(side="left", padx=(0 if idx == 0 else 18, 0))
                tk.Label(grp, text=f"#{inst['name']}", font=("Segoe UI", 8, "bold"), bg=tool["light"], fg=tool["color"]).pack(side="left", padx=(0, 4))
                dot = tk.Label(grp, text="\u25cf", font=("Segoe UI", 11), bg=tool["light"], fg=GREY_ST)
                dot.pack(side="left")
                slbl = tk.Label(grp, text="IDLE", font=("Segoe UI", 8, "bold"), bg=tool["light"], fg=GREY_ST)
                slbl.pack(side="left", padx=(3, 0))
                self._dots[iid]  = dot
                self._slbls[iid] = slbl
        else:
            dot = tk.Label(ss_inner, text="\u25cf", font=("Segoe UI", 11), bg=tool["light"], fg=GREY_ST)
            dot.pack(side="left")
            slbl = tk.Label(ss_inner, text="IDLE", font=("Segoe UI", 8, "bold"), bg=tool["light"], fg=GREY_ST)
            slbl.pack(side="left", padx=(3, 0))
            self._dots[tid]  = dot
            self._slbls[tid] = slbl

        tag_lbl = tk.Label(ss_inner, text=tool["tag"], font=("Courier", 8), bg=tool["light"], fg=tool["color"])
        tag_lbl.pack(side="right")

        body = tk.Frame(card, bg=CARD, padx=20, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=tool["desc"], font=("Segoe UI", 9), bg=CARD, fg=TEXT2, justify="left", anchor="w", wraplength=250).pack(fill="x", anchor="w")
        tk.Frame(body, bg=BORD, height=1).pack(fill="x", pady=(12, 12))

        br = tk.Frame(body, bg=CARD)
        br.pack(fill="x")

        if "instances" in tool:
            for idx, inst in enumerate(tool["instances"]):
                iid = inst["id"]
                pair = tk.Frame(br, bg=CARD)
                pair.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 8, 0))
                lb = tk.Button(pair, text=f"\u25b6 L.{inst['name']}", font=("Segoe UI", 9, "bold"), bg=tool["color"], fg=WHITE, relief="flat", padx=8, pady=9, cursor="hand2", bd=0, activebackground=tool["dark"], activeforeground=WHITE, command=lambda u=inst: launch_tool(u, self._cb))
                lb.pack(side="left", fill="x", expand=True, padx=(0, 4))
                sb = tk.Button(pair, text=f"\u25a0", font=("Segoe UI", 9, "bold"), bg=BG, fg=MUTED, relief="flat", padx=8, pady=9, cursor="hand2", bd=0, state="disabled", activebackground="#FFEBEE", activeforeground=RED_A, command=lambda u=inst: stop_tool(u, self._cb))
                sb.pack(side="left")
                self._lbtns[iid] = lb
                self._sbtns[iid] = sb
        else:
            lb = tk.Button(br, text="\u25b6  Launch Tool", font=("Segoe UI", 10, "bold"), bg=tool["color"], fg=WHITE, relief="flat", padx=12, pady=9, cursor="hand2", bd=0, activebackground=tool["dark"], activeforeground=WHITE, command=lambda t=tool: launch_tool(t, self._cb))
            lb.pack(side="left", fill="x", expand=True, padx=(0, 6))
            sb = tk.Button(br, text="\u25a0  Stop", font=("Segoe UI", 9, "bold"), bg=BG, fg=MUTED, relief="flat", padx=10, pady=9, cursor="hand2", bd=0, state="disabled", activebackground="#FFEBEE", activeforeground=RED_A, command=lambda t=tool: stop_tool(t, self._cb))
            sb.pack(side="left")
            self._lbtns[tid] = lb
            self._sbtns[tid] = sb

    # ── Footer ────────────────────────────────────────────────────────────────
    def _footer(self):
        tk.Frame(self.root, bg=BORD, height=1).pack(fill="x")
        foot = tk.Frame(self.root, bg=PANEL, pady=10)
        foot.pack(fill="x")

        left_f = tk.Frame(foot, bg=PANEL)
        left_f.pack(side="left", padx=32)
        tk.Label(left_f, text="\u00a9 2026  SIFY Technologies", font=("Segoe UI", 8), bg=PANEL, fg=MUTED).pack(side="left")

        right_f = tk.Frame(foot, bg=PANEL)
        right_f.pack(side="right", padx=32)
        tk.Label(right_f, text="\u2605  All tools local  \u00b7  Encrypted Session Instance Node Validation Mode Active", font=("Segoe UI", 8), bg=PANEL, fg=MUTED).pack(side="right")

    def _cb(self, tid, state):
        def _upd():
            tool = _find_tool_for_id(tid)
            cm = {
                "starting": (AMBER_A, "STARTING..."),
                "running":  (GREEN_A, "RUNNING"),
                "stopped":  (ERR_A,   "STOPPED"),
                "error":    (ERR_A,   "ERROR"),
                "idle":     (GREY_ST, "IDLE"),
            }
            col, lbl = cm.get(state, (GREY_ST, state.upper()))

            if tid in self._dots:
                self._dots[tid].config(fg=col)
                self._slbls[tid].config(fg=col, text=lbl)

            running = state == "running"
            dead    = state in ("stopped", "idle", "error")

            if tid in self._lbtns: self._lbtns[tid].config(state="normal" if dead else "disabled")
            if tid in self._sbtns:
                self._sbtns[tid].config(
                    state="normal" if running else "disabled",
                    bg="#FFEBEE" if running else BG,
                    fg=RED_A     if running else MUTED)

            if state == "starting": self._pulse(tid, col)
            else:
                j = self._pjobs.pop(tid, None)
                if j:
                    try: self.root.after_cancel(j)
                    except: pass
        self.root.after(0, _upd)

    def _pulse(self, tid, col, on=True):
        if states.get(tid) != "starting": return
        if tid not in self._dots: return
        tool = _find_tool_for_id(tid)
        light = tool["light"] if tool else WHITE
        self._dots[tid].config(fg=col if on else light)
        self._pjobs[tid] = self.root.after(420, lambda: self._pulse(tid, col, not on))

    def _poll(self):
        for u in _all_units():
            tid = u["id"]
            p = procs.get(tid)
            if p and p.poll() is not None and states[tid] == "running":
                states[tid] = "stopped"; self._cb(tid, "stopped")
        self.root.after(3000, self._poll)

if __name__ == "__main__":
    root = tk.Tk()
    Hub(root)
    root.mainloop()