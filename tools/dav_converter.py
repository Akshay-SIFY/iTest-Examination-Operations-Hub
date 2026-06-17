#!/usr/bin/env python3
# =============================================================================
#  DAV to MP4 Converter — Desktop App (Tkinter)
#  Akshay Singh | iTest Content Team | SIFY Technologies
#
#  Original ffmpeg logic 100% unchanged.
#  Converted from Flask web app to tkinter desktop app.
# =============================================================================

import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path

# ── Colors (matches Hub theme) ───────────────────────────────────────────────
BG     = "#0d0d1a"
CARD   = "#16213e"
CARD2  = "#1a1a35"
BORD   = "#1f2f5a"
STRIPE = "#1a472a"
ACCENT = "#2d6a4f"
ACCH   = "#40916c"
WHITE  = "#f0f4ff"
MUTED  = "#8892b0"
GREEN  = "#00e676"
AMBER  = "#ffc107"
ERR    = "#f44336"
PANEL  = "#12122a"


# =============================================================================
#  ORIGINAL LOGIC — NOT MODIFIED
# =============================================================================
def convert_dav_to_mp4(folder_path, log):
    folder = Path(folder_path)

    if not folder.is_dir():
        log(f"[ERROR] '{folder_path}' is not a valid directory.\n", ERR)
        return

    dav_files = [f for f in folder.rglob("*") if f.suffix.lower() == ".dav"]
    if not dav_files:
        log("No .dav files found in this folder.\n", AMBER)
        return

    log(f"Found {len(dav_files)} .dav file(s).\n\n", GREEN)

    for dav_file in dav_files:
        output_file = dav_file.with_suffix(".mp4")

        if output_file.exists():
            log(f"Skipping (already exists): {output_file.name}\n", MUTED)
            continue

        log(f"Converting:  {dav_file.name}\n         ->  {output_file.name}\n")

        cmd = ["ffmpeg", "-i", str(dav_file), "-c", "copy", "-y", str(output_file)]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        if result.returncode == 0:
            log(f"  \u2714  Done: {output_file.name}\n", GREEN)
        else:
            log("  \u26a0  Stream copy failed, retrying with re-encode...\n", AMBER)
            cmd2 = [
                "ffmpeg", "-i", str(dav_file),
                "-c:v", "libx264", "-preset", "fast",
                "-crf", "23", "-c:a", "aac", "-y", str(output_file)
            ]
            result2 = subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result2.returncode == 0:
                log(f"  \u2714  Done (re-encoded): {output_file.name}\n", GREEN)
            else:
                log(f"  \u2718  Failed: {dav_file.name}\n", ERR)

    log("\n\u2714  All done.\n", GREEN)


# =============================================================================
#  TKINTER UI
# =============================================================================
def launch():
    root = tk.Tk()
    root.title("DAV to MP4 Converter  \u00b7  iTest Video Tools")
    root.geometry("700x560")
    root.configure(bg=BG)
    root.resizable(True, True)

    # ── Top stripe ───────────────────────────────────────────────────
    tk.Frame(root, bg=STRIPE, height=4).pack(fill="x")

    # ── Header ───────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=BG, pady=16, padx=28)
    hdr.pack(fill="x")

    title_row = tk.Frame(hdr, bg=BG)
    title_row.pack(anchor="w")
    tk.Label(title_row, text="\U0001f504 ",
             font=("Segoe UI Emoji", 20), bg=BG, fg=WHITE).pack(side="left")
    tk.Label(title_row, text="DAV \u2192 MP4 Converter",
             font=("Segoe UI", 18, "bold"), bg=BG, fg=WHITE).pack(side="left")

    tk.Label(hdr,
             text="Convert Hikvision / Dahua .dav CCTV recordings to MP4 format",
             font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(3, 0))
    tk.Label(hdr,
             text="Akshay Singh  \u00b7  iTest Content Team  \u00b7  SIFY Technologies",
             font=("Segoe UI", 8), bg=BG, fg="#4a5568").pack(anchor="w")

    tk.Frame(root, bg=BORD, height=1).pack(fill="x", padx=28)

    # ── Folder selector ──────────────────────────────────────────────
    folder_var = tk.StringVar()

    sel = tk.Frame(root, bg=BG, padx=28, pady=18)
    sel.pack(fill="x")

    tk.Label(sel, text="SOURCE FOLDER",
             font=("Segoe UI", 8, "bold"), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 5))

    row = tk.Frame(sel, bg=BG)
    row.pack(fill="x")

    entry = tk.Entry(row, textvariable=folder_var,
                     bg=CARD, fg=WHITE, insertbackground=WHITE,
                     relief="flat", font=("Segoe UI", 10),
                     highlightthickness=1,
                     highlightbackground=BORD,
                     highlightcolor=ACCENT)
    entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))

    def browse():
        path = filedialog.askdirectory(
            title="Select folder containing .dav files")
        if path:
            folder_var.set(path)

    tk.Button(row, text="Browse\u2026",
              font=("Segoe UI", 9), bg=CARD, fg=WHITE,
              relief="flat", padx=14, pady=6, cursor="hand2",
              activebackground=ACCENT, activeforeground=WHITE,
              command=browse).pack(side="left")

    # ── Info box ─────────────────────────────────────────────────────
    info = tk.Frame(sel, bg=CARD2, pady=8, padx=12)
    info.pack(fill="x", pady=(10, 0))
    tk.Label(info,
             text="\u2139  Sub-folders are scanned recursively.  "
                  "Already-converted files are skipped automatically.",
             font=("Segoe UI", 8), bg=CARD2, fg=MUTED,
             justify="left", anchor="w").pack(anchor="w")

    # ── Log box ──────────────────────────────────────────────────────
    log_outer = tk.Frame(root, bg=BG, padx=28)
    log_outer.pack(fill="both", expand=True)

    tk.Label(log_outer, text="OUTPUT LOG",
             font=("Segoe UI", 8, "bold"), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 5))

    log_box = scrolledtext.ScrolledText(
        log_outer,
        bg=CARD, fg=GREEN,
        font=("Consolas", 9), relief="flat",
        insertbackground=WHITE,
        highlightthickness=1, highlightbackground=BORD,
        wrap="word"
    )
    log_box.pack(fill="both", expand=True)
    log_box.tag_configure("green",  foreground=GREEN)
    log_box.tag_configure("amber",  foreground=AMBER)
    log_box.tag_configure("red",    foreground=ERR)
    log_box.tag_configure("muted",  foreground=MUTED)
    log_box.tag_configure("white",  foreground=WHITE)

    def log(msg, color=None):
        log_box.config(state="normal")
        tag = {GREEN: "green", AMBER: "amber", ERR: "red",
               MUTED: "muted", WHITE: "white"}.get(color, "green")
        log_box.insert(tk.END, msg, tag)
        log_box.see(tk.END)

    # ── Button bar ───────────────────────────────────────────────────
    bar = tk.Frame(root, bg=BG, padx=28, pady=14)
    bar.pack(fill="x")

    status_lbl = tk.Label(bar, text="", font=("Segoe UI", 9),
                           bg=BG, fg=MUTED)
    status_lbl.pack(side="left")

    tk.Button(bar, text="Clear Log",
              font=("Segoe UI", 9), bg=CARD, fg=MUTED,
              relief="flat", padx=14, pady=7, cursor="hand2",
              command=lambda: log_box.delete(1.0, tk.END)
              ).pack(side="right", padx=(8, 0))

    convert_btn = tk.Button(
        bar, text="\u25b6  Convert All",
        font=("Segoe UI", 11, "bold"),
        bg=ACCENT, fg=WHITE,
        relief="flat", padx=22, pady=8, cursor="hand2",
        activebackground=ACCH, activeforeground=WHITE,
    )
    convert_btn.pack(side="right")

    def start_convert():
        folder = folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror(
                "Invalid Folder",
                "Please select a valid folder containing .dav files.")
            return
        convert_btn.config(state="disabled", text="\u23f3  Converting\u2026")
        status_lbl.config(text="Processing\u2026", fg=AMBER)
        log_box.delete(1.0, tk.END)

        def run():
            convert_dav_to_mp4(folder, log)
            convert_btn.config(state="normal", text="\u25b6  Convert All")
            status_lbl.config(text="Complete.", fg=GREEN)

        threading.Thread(target=run, daemon=True).start()

    convert_btn.config(command=start_convert)

    # ── Footer ───────────────────────────────────────────────────────
    tk.Frame(root, bg=BORD, height=1).pack(fill="x")
    tk.Label(root,
             text="iTest Video Tools Hub  \u00b7  SIFY Technologies  \u00b7  2026",
             font=("Segoe UI", 8), bg=PANEL, fg="#4a5568", pady=6).pack()

    root.mainloop()


if __name__ == "__main__":
    launch()
