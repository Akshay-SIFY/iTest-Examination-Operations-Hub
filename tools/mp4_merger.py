#!/usr/bin/env python3
# =============================================================================
#  MP4 Merger — iTest Video Tools Hub
#  Original logic 100% unchanged. Only visual theme updated.
#  Akshay Singh | iTest Content Team | SIFY Technologies
# =============================================================================

import os
import re
import glob
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# ---------------------------------------------------------------------------
#  COLORS (matches Hub theme)
# ---------------------------------------------------------------------------
BG_DARK   = "#0d0d1a"
BG_CARD   = "#16213e"
BG_CARD2  = "#1a1a35"
ACCENT    = "#7b2d8b"
WHITE     = "#f0f4ff"
MUTED     = "#8892b0"
SUCCESS   = "#00e676"
ERROR     = "#f44336"
BORDER    = "#1f2f5a"


# ---------------------------------------------------------------------------
#  ORIGINAL LOGIC — NOT MODIFIED
# ---------------------------------------------------------------------------
def merge_videos(folder, log):
    pattern = re.compile(r'(.+?)[-_](\d{14})[-_](\d{14})')
    groups = {}
    for f in glob.glob(os.path.join(folder, '*.mp4')):
        m = pattern.search(os.path.basename(f))
        if m:
            prefix = m.group(1)
            start_time = m.group(2)
            end_time = m.group(3)
            groups.setdefault(prefix, []).append((start_time, end_time, f))

    if not groups:
        log("No matching mp4 files found.\n")
        return

    for prefix, files in groups.items():
        files.sort(key=lambda x: x[0])

        list_path = os.path.join(folder, f'filelist_{prefix}.txt')
        with open(list_path, 'w', encoding='utf-8') as f:
            for _, _, path in files:
                f.write(f"file '{os.path.abspath(path)}'\n")
                log(f"[{prefix}] Adding: {os.path.basename(path)}\n")

        first_start = files[0][0]
        last_end    = files[-1][1]
        out_name    = f"merged-{prefix}-{first_start}-{last_end}.mp4"
        out_path    = os.path.join(folder, out_name)

        cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_path,
               '-c', 'copy', out_path, '-y']
        log(f"\nRunning ffmpeg for {prefix}...\n")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                log(f"\n✔  Done! Saved as: {out_path}\n")
            else:
                log(f"\n✘  Error:\n{result.stderr}\n")
        except FileNotFoundError:
            log("\n✘  ffmpeg not found. Make sure it's installed and in PATH.\n")
        finally:
            if os.path.exists(list_path):
                os.remove(list_path)

        log("\n" + "─" * 52 + "\n")


# ---------------------------------------------------------------------------
#  UI
# ---------------------------------------------------------------------------
def launch():
    root = tk.Tk()
    root.title("MP4 Merger · iTest Video Tools")
    root.geometry("680x520")
    root.configure(bg=BG_DARK)
    root.resizable(True, True)

    # ── Top stripe ──────────────────────────────────────────────────
    tk.Frame(root, bg=ACCENT, height=4).pack(fill="x")

    # ── Header ──────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=BG_DARK, pady=16, padx=28)
    hdr.pack(fill="x")

    title_row = tk.Frame(hdr, bg=BG_DARK)
    title_row.pack(anchor="w")

    tk.Label(title_row, text="🎬 ", font=("Segoe UI Emoji", 20),
             bg=BG_DARK, fg=WHITE).pack(side="left")
    tk.Label(title_row, text="MP4 Merger",
             font=("Segoe UI", 18, "bold"),
             bg=BG_DARK, fg=WHITE).pack(side="left")

    tk.Label(hdr,
             text="Merge segmented MP4 files by camera prefix using ffmpeg concat",
             font=("Segoe UI", 9), bg=BG_DARK, fg=MUTED).pack(anchor="w", pady=(3, 0))

    tk.Label(hdr,
             text="Akshay Singh  ·  iTest Content Team  ·  SIFY Technologies",
             font=("Segoe UI", 8), bg=BG_DARK, fg="#4a5568").pack(anchor="w")

    # ── Divider ─────────────────────────────────────────────────────
    tk.Frame(root, bg=BORDER, height=1).pack(fill="x", padx=28)

    # ── Folder selector ─────────────────────────────────────────────
    folder_var = tk.StringVar()

    sel_frame = tk.Frame(root, bg=BG_DARK, padx=28, pady=18)
    sel_frame.pack(fill="x")

    tk.Label(sel_frame, text="Source Folder",
             font=("Segoe UI", 9, "bold"),
             bg=BG_DARK, fg=MUTED).pack(anchor="w", pady=(0, 5))

    row = tk.Frame(sel_frame, bg=BG_DARK)
    row.pack(fill="x")

    entry = tk.Entry(row, textvariable=folder_var,
                     bg=BG_CARD, fg=WHITE, insertbackground=WHITE,
                     relief="flat", font=("Segoe UI", 10),
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
    entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

    def browse():
        path = filedialog.askdirectory(title="Select folder containing segmented MP4s")
        if path:
            folder_var.set(path)

    tk.Button(row, text="Browse…",
              font=("Segoe UI", 9),
              bg=BG_CARD, fg=WHITE,
              relief="flat", padx=14, pady=6, cursor="hand2",
              activebackground=ACCENT, activeforeground=WHITE,
              command=browse).pack(side="left")

    # ── Log box ─────────────────────────────────────────────────────
    log_outer = tk.Frame(root, bg=BG_DARK, padx=28)
    log_outer.pack(fill="both", expand=True)

    tk.Label(log_outer, text="Output Log",
             font=("Segoe UI", 9, "bold"),
             bg=BG_DARK, fg=MUTED).pack(anchor="w", pady=(0, 5))

    log_box = scrolledtext.ScrolledText(
        log_outer,
        bg=BG_CARD, fg=SUCCESS,
        font=("Consolas", 9), relief="flat",
        insertbackground=WHITE,
        highlightthickness=1, highlightbackground=BORDER,
        wrap="word"
    )
    log_box.pack(fill="both", expand=True)

    def log(msg):
        log_box.config(state="normal")
        log_box.insert(tk.END, msg)
        log_box.see(tk.END)

    # ── Action buttons ───────────────────────────────────────────────
    btn_bar = tk.Frame(root, bg=BG_DARK, padx=28, pady=14)
    btn_bar.pack(fill="x")

    status_lbl = tk.Label(btn_bar, text="",
                           font=("Segoe UI", 9),
                           bg=BG_DARK, fg=MUTED)
    status_lbl.pack(side="left")

    clear_btn = tk.Button(
        btn_bar, text="Clear Log",
        font=("Segoe UI", 9),
        bg=BG_CARD, fg=MUTED,
        relief="flat", padx=14, pady=7, cursor="hand2",
        command=lambda: log_box.delete(1.0, tk.END)
    )
    clear_btn.pack(side="right", padx=(8, 0))

    merge_btn = tk.Button(
        btn_bar, text="▶  Merge Videos",
        font=("Segoe UI", 11, "bold"),
        bg=ACCENT, fg=WHITE,
        relief="flat", padx=22, pady=8, cursor="hand2",
        activebackground="#9b3dab", activeforeground=WHITE,
    )
    merge_btn.pack(side="right")

    def start_merge():
        folder = folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Invalid Folder",
                                 "Please select a valid folder containing MP4 files.")
            return

        merge_btn.config(state="disabled", text="⏳  Merging…")
        status_lbl.config(text="Processing…", fg="#ffc107")
        log_box.delete(1.0, tk.END)

        def run():
            merge_videos(folder, log)
            merge_btn.config(state="normal", text="▶  Merge Videos")
            status_lbl.config(text="Complete.", fg=SUCCESS)

        threading.Thread(target=run, daemon=True).start()

    merge_btn.config(command=start_merge)

    # ── Bottom credit ────────────────────────────────────────────────
    tk.Frame(root, bg=BORDER, height=1).pack(fill="x")
    tk.Label(root, text="iTest Video Tools Hub  ·  SIFY Technologies  ·  2026",
             font=("Segoe UI", 8), bg=BG_DARK, fg="#4a5568", pady=6).pack()

    root.mainloop()


if __name__ == "__main__":
    launch()
