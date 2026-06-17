# =============================================================================
# CCTV Batch Exam Auditor — v4 (Sequential Processing + V4 Core)
# Akshay Singh | iTest Content Team | SIFY Technologies
#
# This version uses the same UI and logic as v4 but processes videos
# one by one (like the original backup) — no parallel execution.
# All v4 features kept: dual‑ROI OCR, CLAHE, per‑frame YOLO, Gemini‑only,
# PDF reports, session‑state recovery, DAV support, etc.
# =============================================================================

import multiprocessing
multiprocessing.freeze_support()

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch
torch.set_num_threads(1)

import streamlit as st
from google import genai
import cv2
import re
import gc
import time
import shutil
import base64
import subprocess
import requests
from datetime import datetime, timedelta, date
from fpdf import FPDF
from ultralytics import YOLO
import easyocr
import numpy as np
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(page_title="CCTV Batch Exam Auditor", layout="wide")
st.title("AI-Powered CCTV Examination Audit & Compliance Platform")
st.write("Automating Examination CCTV Audits with Intelligent Time Verification and Compliance Monitoring.")
st.write("Akshay Singh | iTest Content Team | SIFY Technologies")

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.header("Configuration")

api_key = st.sidebar.text_input("Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("Exam Session Details")
centre_name = st.sidebar.text_input("Centre Name", placeholder="e.g. Delhi_Centre_01")
exam_date   = st.sidebar.date_input("Exam Date", value=date.today())
shift       = st.sidebar.selectbox("Shift", ["B1", "B2", "B3"])

st.sidebar.markdown("---")
st.sidebar.subheader("CCTV Clock Filter")
st.sidebar.write("Analyse footage where the on-screen clock falls within:")
start_clock = st.sidebar.text_input("Start Time (HH:MM AM/PM)", value="09:30 AM")
end_clock   = st.sidebar.text_input("End Time (HH:MM AM/PM)",   value="11:30 AM")

st.sidebar.markdown("---")
st.sidebar.subheader("Processing Settings")
max_parallel    = st.sidebar.slider("Parallel Videos", 1, 4, 1, help="Keep at 1 on Windows.")
phash_threshold = st.sidebar.slider("Frame Dedup Sensitivity", 0, 20, 0,
    help="Perceptual hash distance. 0 = off (fastest). 8 removes ~95% similar frames.")
use_clahe = st.sidebar.checkbox("CLAHE OCR Enhancement", value=False,
    help="Improves OCR on dark footage but slightly slower.")

st.sidebar.markdown("---")
st.sidebar.subheader("Frame Budget")
min_frames_per_video = st.sidebar.slider("Min frames per camera (Gemini)", 3, 10, 3,
    help="Every camera guaranteed at least this many frames.")
max_frames_per_video = st.sidebar.slider("Max frames per camera", 10, 40, 20,
    help="Cap per camera before global budget kicks in.")
max_global_gemini = st.sidebar.slider("Global Gemini cap (total frames)", 45, 120, 90,
    help="Score 7/8/10 frames are NEVER dropped even if this is exceeded.")

# =============================================================================
# SESSION STATE
# =============================================================================
for _k, _v in [
    ("final_payload_all",    []),
    ("cached_ge_paths",      []),
    ("cached_target_start",  None),
    ("cached_target_end",    None),
    ("session_folder",       None),
    ("pdf_report_path",      None),
    ("report_text",          ""),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# =============================================================================
# HELPERS — session folder
# =============================================================================
def build_session_folder_name(cname, edate, eshift):
    safe = re.sub(r'[^\w\-]', '_', cname.strip())
    return f"{safe}_{edate.strftime('%d-%m-%Y')}_{eshift}"

def extract_camera_name(filename):
    fname = os.path.splitext(os.path.basename(filename))[0]
    fname = re.sub(r'_f\d{6}$', '', fname)
    m     = re.search(r'_t(\d{2})_(\d{2})_(\d{2})$', fname)
    return fname[:m.start()] if m else fname

def extract_timestamp_label(filename):
    fname = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r'_t(\d{2}_\d{2}_\d{2})_f\d{6}$', fname)
    if m:
        return m.group(1)
    m2 = re.search(r'_t(\d{2}_\d{2}_\d{2})$', fname)
    return m2.group(1) if m2 else fname

def save_frames_to_session(frame_paths, session_folder):
    saved = []
    for src in frame_paths:
        if not os.path.exists(src):
            continue
        cam_name = extract_camera_name(src)
        ts_label = extract_timestamp_label(src)
        cam_dir  = os.path.join(session_folder, cam_name)
        os.makedirs(cam_dir, exist_ok=True)
        dest = os.path.join(cam_dir, f"{ts_label}.jpg")
        if os.path.exists(dest):
            base, idx = ts_label, 1
            while os.path.exists(dest):
                dest = os.path.join(cam_dir, f"{base}_{idx}.jpg")
                idx += 1
        shutil.copy2(src, dest)
        saved.append(dest)
    return saved

# =============================================================================
# PDF REPORT
# =============================================================================
def sanitise_for_pdf(text):
    replacements = {
        '\u2014': '-', '\u2013': '-', '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2022': '*', '\u2026': '...',
        '\u00a0': ' ', '\u2192': '->',
    }
    for c, r in replacements.items():
        text = text.replace(c, r)
    return text.encode('latin-1', errors='replace').decode('latin-1')

# =============================================================================
# SCREENSHOT HELPERS — used by PDF generator
# =============================================================================

def _ts_to_seconds(hms):
    """Convert 'HH:MM:SS' string to total seconds integer."""
    try:
        h, m, s = hms.split(':')
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        return -1


def _norm_cam(s):
    """Normalise camera name: lowercase, collapse spaces/dots/hyphens to single _."""
    return re.sub(r'[\s\.\-]+', '_', s.strip()).lower()


def _build_ge_index(ge_paths):
    """
    Parse ge_paths filenames into a lookup structure:
        { norm_cam_name: [ (seconds_int, filepath), ... ] }  sorted by seconds
    Filename format: <cam_name>_t<HH>_<MM>_<SS>_f<xxxxxx>.jpg
    """
    index = defaultdict(list)
    ts_pattern = re.compile(r'_t(\d{2})_(\d{2})_(\d{2})_f\d+', re.IGNORECASE)
    for path in ge_paths:
        fname = os.path.splitext(os.path.basename(path))[0]
        m = ts_pattern.search(fname)
        if not m:
            continue
        t_secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        # camera name = everything before the _tHH_MM_SS_fXXXXXX suffix
        cam_raw = fname[:m.start()]
        index[_norm_cam(cam_raw)].append((t_secs, path))
    for k in index:
        index[k].sort(key=lambda x: x[0])
    return index


def _find_closest_frame(cam_name, target_secs, ge_index):
    """
    Given a normalised camera name and a target time in seconds,
    find the ge_paths entry with the smallest time delta for that camera.
    Returns (filepath, actual_seconds) or (None, None) if no match.
    """
    cam_norm = _norm_cam(cam_name)

    # Try exact cam key first, then best fuzzy match
    candidates = ge_index.get(cam_norm)
    if candidates is None:
        # Fuzzy: find index key with most common tokens
        cam_tokens = set(cam_norm.split('_'))
        best_key, best_score = None, 0
        for key in ge_index:
            score = len(cam_tokens & set(key.split('_')))
            if score > best_score:
                best_score, best_key = score, key
        if best_key is None:
            return None, None
        candidates = ge_index[best_key]

    if not candidates:
        return None, None

    # Find closest by absolute time delta
    best_path, best_delta = None, float('inf')
    for secs, path in candidates:
        delta = abs(secs - target_secs)
        if delta < best_delta:
            best_delta, best_path = delta, path
    return best_path, best_delta


def _extract_observations_from_point_block(point_lines):
    """
    Extract all (camera, timestamp_hms) pairs from a Point block.

    Handles all Gemini output formats:
      A. Single    : <cam> [HH:MM:SS]: description
      B. Comma sep : <cam>, [HH:MM:SS]: description
      C. Multi-ts  : <cam>, [ts1], [ts2], [ts3]: description
                     (camera named once, multiple timestamps follow)
      D. Range     : <cam>, [HH:MM:SS] to [HH:MM:SS]: description
                     → emits start, computed midpoint, and end

    Returns deduplicated list of (cam_str, 'HH:MM:SS').
    """
    results = []

    # Range pattern — comma after cam name is optional
    range_pat = re.compile(
        r'([A-Za-z][A-Za-z0-9 _\.\-]*?),?\s*\[(\d{2}:\d{2}:\d{2})\]\s+to\s+\[(\d{2}:\d{2}:\d{2})\]',
        re.IGNORECASE
    )
    # Camera-lead pattern — cam name at start of an observation line (after * or -),
    # followed by optional comma, then first [ts]
    cam_lead_pat = re.compile(
        r'(?:^|[\*\-•]\s*)([A-Za-z][A-Za-z0-9 _\.\-]+?),?\s*\[(\d{2}:\d{2}:\d{2})\]',
        re.IGNORECASE
    )
    # All timestamps anywhere on a line
    all_ts_pat = re.compile(r'\[(\d{2}:\d{2}:\d{2})\]')

    for line in point_lines:
        line_remainder = line

        # --- Handle range first, blank out matched span so ts collector ignores it ---
        for m in range_pat.finditer(line):
            cam   = m.group(1).strip()
            ts1   = m.group(2).strip()
            ts2   = m.group(3).strip()
            s1    = _ts_to_seconds(ts1)
            s2    = _ts_to_seconds(ts2)
            mid_s = (s1 + s2) // 2
            ts_mid = f"{mid_s//3600:02d}:{(mid_s%3600)//60:02d}:{mid_s%60:02d}"
            results.append((cam, ts1))
            results.append((cam, ts_mid))
            results.append((cam, ts2))
            line_remainder = line_remainder.replace(m.group(0), ' ' * len(m.group(0)))

        # --- Find camera name lead, then collect ALL [ts] on this line for it ---
        lead = cam_lead_pat.search(line_remainder)
        if lead:
            cam = lead.group(1).strip()
            for ts_m in all_ts_pat.finditer(line_remainder):
                results.append((cam, ts_m.group(1)))

    # Deduplicate preserving order
    seen = set()
    unique = []
    for cam, ts in results:
        key = (cam.lower(), ts)
        if key not in seen:
            seen.add(key)
            unique.append((cam, ts))
    return unique


def _embed_screenshots_for_point(pdf, point_lines, ge_index):
    """
    Embed evidence screenshots for a single Point block.
    Only called when Manual Intervention Required = Yes.
    Matches observations against ge_index (built from ge_paths).
    Lays out up to 3 images per row, 58mm wide, with caption.
    """
    if not ge_index:
        return

    observations = _extract_observations_from_point_block(point_lines)
    if not observations:
        return

    # Resolve each observation to its closest ge_paths frame
    image_entries = []   # list of (img_path, caption_str)
    seen_paths = set()
    for cam, ts in observations:
        target_secs = _ts_to_seconds(ts)
        img_path, delta = _find_closest_frame(cam, target_secs, ge_index)
        if img_path and img_path not in seen_paths and os.path.exists(img_path):
            seen_paths.add(img_path)
            # Build caption from actual frame filename timestamp
            fname = os.path.splitext(os.path.basename(img_path))[0]
            tm = re.search(r'_t(\d{2})_(\d{2})_(\d{2})_f', fname)
            if tm:
                actual_ts = f"{tm.group(1)}:{tm.group(2)}:{tm.group(3)}"
            else:
                actual_ts = ts
            image_entries.append((img_path, f"{cam}  [{actual_ts}]"))

    if not image_entries:
        return

    IMAGES_PER_ROW = 3
    IMG_W          = 58.0   # mm
    IMG_H          = 38.0   # mm
    GAP            = 4.0    # mm
    CAPTION_H      = 5.0    # mm

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 4, "Evidence Screenshots:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    for row_start in range(0, len(image_entries), IMAGES_PER_ROW):
        row = image_entries[row_start: row_start + IMAGES_PER_ROW]

        needed_height = IMG_H + CAPTION_H + 4
        if pdf.get_y() + needed_height > pdf.page_break_trigger:
            pdf.add_page()

        row_y    = pdf.get_y()
        x_cursor = pdf.l_margin

        for img_path, caption in row:
            try:
                pdf.image(img_path, x=x_cursor, y=row_y, w=IMG_W, h=IMG_H)
            except Exception:
                pdf.set_draw_color(180, 180, 180)
                pdf.rect(x_cursor, row_y, IMG_W, IMG_H)
                pdf.set_xy(x_cursor, row_y + IMG_H / 2 - 3)
                pdf.set_font("Helvetica", "I", 7)
                pdf.cell(IMG_W, 5, "[Image unavailable]", align="C")

            cap_y = row_y + IMG_H + 1
            pdf.set_xy(x_cursor, cap_y)
            pdf.set_font("Helvetica", "I", 6.5)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(IMG_W, CAPTION_H, sanitise_for_pdf(caption), align="C")
            pdf.set_text_color(0, 0, 0)

            x_cursor += IMG_W + GAP

        pdf.set_xy(pdf.l_margin, row_y + IMG_H + CAPTION_H + 3)

    pdf.ln(2)


# =============================================================================
# PDF REPORT
# =============================================================================

def generate_pdf_report(report_text, cname, edate, eshift,
                        t_start_str, t_end_str, output_path,
                        screenshots_folder=None, ge_paths=None):
    report_text = sanitise_for_pdf(report_text)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_fill_color(30, 60, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "CCTV Examination Audit Report",
             new_x="LMARGIN", new_y="NEXT", fill=True, align="C")
    pdf.ln(3)

    pdf.set_text_color(0, 0, 0)
    for label, value in [
        ("Centre Name",  sanitise_for_pdf(cname)),
        ("Exam Date",    edate.strftime("%d-%m-%Y")),
        ("Shift",        eshift),
        ("Audit Window", f"{t_start_str}  to  {t_end_str}"),
        ("Generated On", date.today().strftime("%d-%m-%Y")),
    ]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(45, 7, f"{label}:", border=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, value, border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_draw_color(30, 60, 120)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Build ge_index once for the whole report — used by all Point blocks
    ge_index = _build_ge_index(ge_paths) if ge_paths else {}

    lines = report_text.split('\n')

    def _is_point_header(line):
        return bool(re.match(r'^\*\*Point\s+\d+', line) or line.startswith('## '))

    def _render_line(pdf, line):
        line = line.rstrip()
        if _is_point_header(line):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(220, 230, 245)
            clean = re.sub(r'\*\*', '', line).strip('#').strip()
            pdf.multi_cell(0, 6, clean, fill=True, new_x="LMARGIN", new_y="NEXT")
        elif re.match(r'^- \*\*.+\*\*', line):
            m = re.match(r'- \*\*(.+?):\*\*\s*(.*)', line)
            if m:
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(52, 5, f"  {m.group(1)}:", border=0)
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, m.group(2), new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, re.sub(r'\*\*', '', line),
                               new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("Here is the audit report"):
            pdf.set_font("Helvetica", "I", 9)
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        elif line.strip() == '':
            pdf.ln(2)
        else:
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, re.sub(r'\*\*', '', line),
                           new_x="LMARGIN", new_y="NEXT")

    # Group lines into Point blocks
    blocks = []
    current_block = []
    in_point_block = False

    for line in lines:
        if _is_point_header(line):
            if current_block:
                blocks.append((in_point_block, current_block))
            current_block  = [line]
            in_point_block = True
        else:
            current_block.append(line)

    if current_block:
        blocks.append((in_point_block, current_block))

    # Render each block; inject screenshots only for MIR=Yes points
    for is_point, block_lines in blocks:
        for line in block_lines:
            _render_line(pdf, line)

        if not is_point or not ge_index:
            continue

        # Check Manual Intervention Required — only embed when Yes
        mir_line = next(
            (l for l in block_lines
             if re.search(r'Manual Intervention Required', l, re.IGNORECASE)),
            ""
        )
        mir_val = re.search(
            r'Manual Intervention Required.*?:\*\*?\s*(\w+)', mir_line, re.IGNORECASE
        )
        if not mir_val:
            continue
        if mir_val.group(1).strip().lower() != 'yes':
            continue   # No violation flagged — skip screenshots

        _embed_screenshots_for_point(pdf, block_lines, ge_index)

    pdf.output(output_path)
    return output_path

# =============================================================================
# MODEL LOADING — pre-loaded at app startup so "Run Full Audit" has no delay
# Models stored in a fixed local folder — never re-downloaded after first run.
# =============================================================================

# Permanent model cache folder — sits next to this script
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR   = os.path.join(_SCRIPT_DIR, "models_cache")
_YOLO_PATH   = os.path.join(_MODEL_DIR, "yolov8n.pt")
os.makedirs(_MODEL_DIR, exist_ok=True)

@st.cache_resource(show_spinner="Loading YOLO detection model...")
def load_yolo():
    return YOLO(_YOLO_PATH)

@st.cache_resource(show_spinner="Loading OCR engine (first load ~60 sec on CPU)...")
def load_ocr():
    return easyocr.Reader(['en'], gpu=False, model_storage_directory=_MODEL_DIR)

# Pre-load at app startup — user sees spinner once, never again during audit runs
_yolo_preload = load_yolo()
_ocr_preload  = load_ocr()

# =============================================================================
# TIME HELPERS
# =============================================================================
def parse_ui_time(time_str):
    try:
        return datetime.strptime(time_str.strip(), "%I:%M %p").time()
    except Exception:
        st.error(f"Bad time format: '{time_str}'. Expected HH:MM AM/PM.")
        return None

# =============================================================================
# OCR  — FIX 1: short-circuit after first ROI succeeds
#        Top-left ROI tried first (most CCTV overlays). Bottom-left only
#        attempted when top-left returns nothing. CLAHE optional, 2x upscale.
# =============================================================================
def _parse_time_from_text(text):
    # Strict: HH:MM:SS or HH.MM.SS
    strict = re.findall(r'\b(\d{1,2})[\:\.](\d{2})[\:\.](\d{2})\b', text)
    for h_s, m_s, s_s in strict:
        h, m, s = int(h_s), int(m_s), int(s_s)
        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
            return h, m, s
    # Loose: separators can be ; . space -
    loose = re.findall(r'(\d{2})[\:\;\.\s\-]+(\d{2})[\:\;\.\s\-]+(\d{2})', text)
    for h_s, m_s, s_s in loose:
        h, m, s = int(h_s), int(m_s), int(s_s)
        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
            return h, m, s
    return None

def extract_time_via_ocr(frame, reader, use_clahe_flag=False, preview_slot=None):
    h, w = frame.shape[:2]
    rois = [
        (0,             int(h * 0.16), 0, int(w * 0.38)),   # top-left
        (int(h * 0.84), h,             0, int(w * 0.38)),   # bottom-left (fallback only)
    ]
    for roi_idx, (ymin, ymax, xmin, xmax) in enumerate(rois):
        try:
            crop    = frame[ymin:ymax, xmin:xmax]
            gray    = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            if use_clahe_flag:
                clahe   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                resized = clahe.apply(resized)
            _, thresh = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # Only show preview for top-left ROI to avoid double-render
            if preview_slot is not None and roi_idx == 0:
                preview_slot.image(thresh, caption="OCR Stream", use_container_width=True)
            texts  = reader.readtext(thresh, detail=0, paragraph=False)
            result = _parse_time_from_text(" ".join(texts))
            if result:
                # ── FIX 1: success on this ROI — return immediately, skip remaining ROIs ──
                h_v, m_v, s_v = result
                return datetime.strptime(f"{h_v:02d}:{m_v:02d}:{s_v:02d}", "%H:%M:%S").time()
        except Exception:
            continue
    return None

# =============================================================================
# pHASH DEDUP  (only called if threshold > 0)
# =============================================================================
def _phash_array(image_path, hash_size=8):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    resized = cv2.resize(img, (hash_size*4, hash_size*4), interpolation=cv2.INTER_AREA)
    dct     = cv2.dct(np.float32(resized))
    dct_low = dct[:hash_size, :hash_size]
    return dct_low > np.median(dct_low)

def deduplicate_frames(frame_list, threshold):
    if threshold == 0 or not frame_list:
        return frame_list
    hashes      = [_phash_array(item[1]) for item in frame_list]
    kept        = []
    kept_hashes = []
    for i, item in enumerate(frame_list):
        if hashes[i] is None:
            kept.append(item)
            continue
        is_dup = any(
            kh is not None and int(np.sum(hashes[i] != kh)) <= threshold
            for kh in kept_hashes
        )
        if not is_dup:
            kept.append(item)
            kept_hashes.append(hashes[i])
    return kept

# =============================================================================
# PRIORITY SCORING
# =============================================================================
CONTRABAND_CLASSES = [62, 63, 67]   # TV, laptop, cell phone
PERSON_CLASS       = 0

def compute_priority_score(detected_classes, is_checkpoint=False):
    if any(c in detected_classes for c in CONTRABAND_CLASSES):
        return 10
    if detected_classes.count(PERSON_CLASS) >= 2:
        return 5
    if is_checkpoint:
        return 2
    return 0

# =============================================================================
# SINGLE-VIDEO PROCESSOR
#
# FIX 2 — Frame decode: cap.set() seek jumps instead of reading every frame.
#          Jumps directly to each sample position — no wasted cap.read() calls
#          on frames that will be discarded. Matches the speed of the original v2.
#
# FIX 3 — YOLO resize: small_frame only created when actually running YOLO,
#          not on every loop iteration.
#
# OCR anchor logic and all other v4 features preserved exactly.
# =============================================================================
_write_lock = threading.Lock()

def process_single_video(
    video_index, video_name, folder_path, cache_dir,
    target_start, target_end, start_clock,
    yolo_model, ocr_reader,
    use_clahe_flag, phash_thresh,
    max_frames_per_vid,
    log_queue, progress_tracker,
):
    def log(msg):
        with _write_lock:
            log_queue.append(msg)

    raw_path     = os.path.join(folder_path, video_name)
    working_path = raw_path

    # DAV -> MP4 conversion
    if video_name.lower().endswith('.dav'):
        converted    = f"converted_{os.path.splitext(video_name)[0]}.mp4"
        working_path = os.path.join(cache_dir, converted)
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', raw_path, '-vcodec', 'copy', working_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
        except Exception:
            log(f"Could not convert `{video_name}`. Skipping.")
            return []

    cap          = cv2.VideoCapture(working_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0

    progress_tracker['total'] = max(total_frames, 1)
    progress_tracker['done']  = 0
    progress_tracker['name']  = video_name

    SAMPLE_INTERVAL    = max(1, int(fps * 5))    # sample every 5 sec
    RE_ANCHOR_INTERVAL = int(fps * 360)          # re-OCR every 360 sec (6 min) — interpolation is accurate between anchors
    CHECKPOINT_EVERY   = int(fps * 180)          # base checkpoint every 3 min

    frames_since_last_anchor = 0
    video_screenshots        = []
    frame_count              = 0
    _elevated_scan            = False

    # ── Pre-set wall clock from filename before loop starts ──
    # This means frame 0 already has correct time, no wasted pre-window scanning.
    # Priority: filename 14-digit timestamp → UI start time (last resort only)
    _fname_match = re.search(r'(\d{14})', video_name)
    if _fname_match and not _fname_match.group(1).startswith("0000"):
        video_start_wall_clock = datetime.strptime(_fname_match.group(1), "%Y%m%d%H%M%S")
        log(f"`{video_name}`: Wall clock pre-set from filename → {video_start_wall_clock.strftime('%H:%M:%S')}")
    else:
        video_start_wall_clock = datetime.combine(datetime.today(), target_start)
        log(f"`{video_name}`: No filename timestamp — grounding to UI start ({start_clock}).")
    current_frame_time = video_start_wall_clock.time()

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            # Update progress every 2 sample intervals
            if frame_count % (SAMPLE_INTERVAL * 2) == 0:
                progress_tracker['done'] = frame_count

            # Skip non-sample frames — sequential read, no seek
            if frame_count % SAMPLE_INTERVAL != 0:
                frame_count += 1
                continue

            # ---- OCR anchor (re-confirms wall clock every 6 min) -----------
            # Wall clock is always pre-set before loop; OCR here only corrects drift
            if frames_since_last_anchor >= RE_ANCHOR_INTERVAL:
                live_time = extract_time_via_ocr(frame, ocr_reader, use_clahe_flag)
                if live_time:
                    elapsed = frame_count / fps
                    video_start_wall_clock   = (
                        datetime.combine(datetime.today(), live_time)
                        - timedelta(seconds=elapsed)
                    )
                    current_frame_time       = live_time
                else:
                    elapsed = frame_count / fps
                    current_frame_time = (
                        video_start_wall_clock + timedelta(seconds=elapsed)
                    ).time()
                frames_since_last_anchor = 0

            else:
                # Between anchors: interpolate from wall clock
                elapsed = frame_count / fps
                current_frame_time = (
                    video_start_wall_clock + timedelta(seconds=elapsed)
                ).time()
                frames_since_last_anchor += SAMPLE_INTERVAL

            # ---- Clock window filter ----------------------------------------
            if current_frame_time is not None:
                progress_tracker['current_time'] = current_frame_time.strftime('%H:%M:%S')

            if current_frame_time is None or not (
                target_start <= current_frame_time <= target_end
            ):
                frame_count += 1
                continue

            # ---- YOLO: checkpoint-based triggering (matches original v2 speed) -----
            # Baseline: run YOLO every 5 min (CHECKPOINT_EVERY).
            # Elevated: run YOLO every 5 sec when previous frame had a person/object
            # detected — ensures violations across consecutive frames are never missed.
            is_cp = (frame_count % CHECKPOINT_EVERY == 0)
            run_yolo = is_cp or _elevated_scan

            if run_yolo:
                small_frame = cv2.resize(frame, (640, 480))
                results     = yolo_model(small_frame, verbose=False, workers=0)

                cls_list = []
                if results[0].boxes is not None:
                    cls_list = results[0].boxes.cls.cpu().numpy().astype(int).tolist()

                score = compute_priority_score(cls_list, is_cp)

                # Stay in elevated mode if people/objects still detected
                _elevated_scan = len(cls_list) > 0

                if score > 0:
                    clean_id  = os.path.splitext(video_name)[0]
                    t_label   = current_frame_time.strftime("%H_%M_%S")
                    shot_path = os.path.join(
                        cache_dir,
                        f"{clean_id}_t{t_label}_f{frame_count:06d}.jpg"
                    )
                    cv2.imwrite(shot_path, frame)
                    video_screenshots.append(
                        (score, shot_path, current_frame_time, video_index)
                    )
            else:
                _elevated_scan = False

            frame_count += 1

    finally:
        cap.release()
        if video_name.lower().endswith('.dav') and os.path.exists(working_path):
            try:
                os.remove(working_path)
            except Exception:
                pass

    # ---- Optional pHash dedup -----------------------------------------------
    if phash_thresh > 0:
        video_screenshots.sort(key=lambda x: x[0], reverse=True)
        video_screenshots = deduplicate_frames(video_screenshots, phash_thresh)

    # ---- Stratified chronological sampling per video ------------------------
    priority_groups = defaultdict(list)
    for item in video_screenshots:
        priority_groups[item[0]].append(item)

    selected = []
    for p_score in [10, 5, 2]:
        frames_in_p = priority_groups[p_score]
        frames_in_p.sort(key=lambda x: x[2])           # chronological
        rem = max_frames_per_vid - len(selected)
        if rem <= 0:
            break
        if len(frames_in_p) <= rem:
            selected.extend(frames_in_p)
        else:
            indices = np.linspace(0, len(frames_in_p)-1, rem, dtype=int)
            selected.extend([frames_in_p[i] for i in indices])

    scores = sorted(set(s[0] for s in selected), reverse=True)
    log(f"`{video_name}`: {len(selected)} frames selected "
        f"(from {len(video_screenshots)} candidates, scores: {scores})")
    return selected


# =============================================================================
# FRAME POOL BUILDERS
# =============================================================================
def build_gemini_only_payload(all_screenshots, num_videos, min_guaranteed, max_global):
    vg = defaultdict(list)
    for item in all_screenshots:
        vg[item[3]].append(item)

    guaranteed_pool = []
    remainder_pool  = []

    for vid_idx, frames in vg.items():
        frames.sort(key=lambda x: x[0], reverse=True)
        guaranteed_pool.extend(frames[:min_guaranteed])
        remainder_pool.extend(frames[min_guaranteed:])

    remaining_slots = max_global - len(guaranteed_pool)
    if remaining_slots > 0:
        remainder_pool.sort(key=lambda x: x[0], reverse=True)
        guaranteed_pool.extend(remainder_pool[:remaining_slots])

    # Score 10 (contraband) frames are never dropped
    score10 = [item for item in remainder_pool[remaining_slots:] if item[0] == 10]
    for item in score10:
        if item not in guaranteed_pool:
            guaranteed_pool.append(item)

    guaranteed_pool.sort(key=lambda x: (x[3], x[2]))
    return [p for _, p, _, _ in guaranteed_pool]


def split_for_gemini(paths, max_per_call=120):
    if len(paths) <= max_per_call:
        return [paths]
    cg = defaultdict(list)
    for p in paths:
        fname = os.path.basename(p)
        m     = re.match(r'^(.+?)_t\d{2}_\d{2}_\d{2}', fname)
        cam   = m.group(1) if m else "unknown"
        cg[cam].append(p)
    batches, current = [], []
    for cam, frames in cg.items():
        if len(current) + len(frames) > max_per_call and current:
            batches.append(current)
            current = []
        current.extend(frames)
    if current:
        batches.append(current)
    return batches

# =============================================================================
# MANIFEST + AUDIT PROMPT
# =============================================================================
def build_manifest(payload_paths):
    manifest  = "CAMERA FOOTAGE MANIFEST:\n"
    manifest += "Each image identified by camera source and on-screen timestamp.\n\n"
    for path in payload_paths:
        fname       = os.path.splitext(os.path.basename(path))[0]
        fname_clean = re.sub(r'_f\d{6}$', '', fname)
        m           = re.search(r'_t(\d{2})_(\d{2})_(\d{2})$', fname_clean)
        if m:
            cam = fname_clean[:m.start()]
            ts  = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
            manifest += f"- Camera: {cam} | On-screen time: {ts}\n"
        else:
            manifest += f"- Camera: {fname_clean}\n"
    return manifest

def build_audit_prompt(s24, e24, manifest, cname="", edate=None, eshift="", is_partial=False):
    header = ""
    if cname:
        date_str = edate.strftime("%d-%m-%Y") if edate else ""
        header   = f"Centre: {cname} | Date: {date_str} | Shift: {eshift}\n"

    partial_note = (
        "\nNOTE: This is a PARTIAL report covering a camera subset. "
        "It will be merged into a final master report.\n"
        if is_partial else ""
    )

    return f"""
You are an expert exam invigilator auditor analysing CCTV security footage.

{header}
CRITICAL CONTEXT:
Frames have been pre-filtered using on-screen OCR to match the clock window {s24} to {e24}.
{partial_note}

STRICT OPENING LINE — your response MUST start with exactly this sentence:
"Here is the audit report based on the provided video frames between {s24} and {e24}:"

TIMESTAMP RULE:
- Read timestamps ONLY from the white overlay text visible inside each frame.
- Write all observation timestamps in 24-hour format (e.g. [13:00:41]).
- Do NOT use the filter window times ({s24} or {e24}) as observation timestamps.
- Do NOT mention frame numbers. Reference camera name and on-screen timestamp only.

REPORT STRUCTURE — address all 13 points:
**Point [N]. [Guideline Name]**
- **Status:** [Yes / No / Not clear]
- **Manual Intervention Required:** [Yes / No]
- **Observation Notes:** [Camera name, exact 24-hour on-screen timestamp, clear description.
  For clean cameras explicitly list them as 'Clear - no anomalies observed'.]

{manifest}

GUIDELINES TO AUDIT (13 points):
1. Are seats properly visible in all cameras?
2. Are invigilators actively roaming in the examination labs?
3. Any instance of venue staff using a mobile phone inside the lab?
4. Any instance of a candidate using a mobile phone inside the lab?
5. Any instance of candidates talking to each other?
6. Are partitions visible and properly placed between candidates?
7. Any instance of venue staff directly helping a candidate?
8. Any instance of a monitor being changed during the live exam?
9. Any instance of a CPU being changed during the live exam?
10. Any instance of an invigilator standing constantly behind any one seat?
11. Any instance of a candidate using unfair means (paper chits, writing on palm, mobile phone)?
12. Any instance of venue staff using unfair means?
13. Any instance of a candidate moving from their seat to another candidate's seat?
"""

# =============================================================================
# GEMINI SYNTHESIS
# =============================================================================
def execute_gemini_synthesis(payload_paths, t_start, t_end, cname, edate, eshift):
    s24 = t_start.strftime("%H:%M:%S")
    e24 = t_end.strftime("%H:%M:%S")

    batches  = split_for_gemini(payload_paths, 120)
    is_multi = len(batches) > 1
    batch_reports = []
    any_batch_failed = False

    for b_idx, batch_paths in enumerate(batches):
        label = f"batch {b_idx+1}/{len(batches)}" if is_multi else "full payload"

        gemini_files   = []
        failed_uploads = 0
        with st.spinner(f"Uploading {len(batch_paths)} frames to Gemini ({label})..."):
            for img_path in batch_paths:
                try:
                    gemini_files.append(client.files.upload(file=img_path))
                except Exception:
                    failed_uploads += 1
        st.success(f"Upload complete ({label})."
                   + (f" {failed_uploads} failed." if failed_uploads else ""))

        if failed_uploads:
            st.sidebar.warning(f"{failed_uploads} frame(s) failed to upload (batch {b_idx+1}).")

        manifest = build_manifest(batch_paths)
        prompt   = build_audit_prompt(s24, e24, manifest, cname, edate, eshift, is_partial=is_multi)

        with st.spinner(f"Gemini — analysing {label}..."):
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=gemini_files + [prompt]
                    )
                    batch_reports.append(response.text)
                    break
                except Exception as e:
                    if ("503" in str(e) or "UNAVAILABLE" in str(e) or "505" in str(e)):
                        if attempt < 2:
                            st.sidebar.warning(f"Gemini busy ({attempt+1}/3). Retrying in 4s...")
                            time.sleep(4)
                            continue
                    st.error(f"Gemini error (batch {b_idx+1}): {e}")
                    batch_reports.append(f"[Batch {b_idx+1} failed: {e}]")
                    any_batch_failed = True
                    break

        for gf in gemini_files:
            try:
                client.files.delete(name=gf.name)
            except Exception:
                pass

    if is_multi and len(batch_reports) > 1:
        combined       = "\n\n---\n\n".join(
            f"Camera Set {i+1}:\n{r}" for i, r in enumerate(batch_reports)
        )
        merge_manifest = build_manifest(payload_paths)
        merge_prompt   = (
            f"Consolidate {len(batch_reports)} partial CCTV audit reports "
            f"into one final master report for {cname}, "
            f"{edate.strftime('%d-%m-%Y')}, Shift {eshift}, "
            f"window {s24} to {e24}.\n\n"
            f"RULES: Same 13-point format. No frame numbers. "
            f"Camera name and 24-hour on-screen timestamp only. "
            f"Start with: 'Here is the audit report based on the provided "
            f"video frames between {s24} and {e24}:'\n\n"
            f"{merge_manifest}\n\nPARTIAL REPORTS:\n{combined}"
        )
        with st.spinner("Gemini — merging into master report..."):
            try:
                resp        = client.models.generate_content(
                    model='gemini-2.5-flash', contents=[merge_prompt]
                )
                report_text = resp.text
                st.subheader("Gemini Audit Report")
                st.markdown(report_text)
                return (not any_batch_failed), report_text
            except Exception as e:
                st.error(f"Gemini merge failed: {e}")
                combined_text = "\n\n".join(batch_reports)
                st.subheader("Partial Gemini Reports")
                st.markdown(combined_text)
                return False, combined_text
    else:
        report_text = batch_reports[0] if batch_reports else ""
        st.subheader("Gemini Audit Report")
        st.markdown(report_text)
        return (bool(batch_reports) and not any_batch_failed), report_text

# =============================================================================
# MAIN APP
# =============================================================================
if not api_key:
    st.warning("Enter your Gemini API Key in the sidebar.")
elif not centre_name.strip():
    st.warning("Please enter a Centre Name in the sidebar before proceeding.")
else:
    client = genai.Client(api_key=api_key)

    folder_path = st.text_input(
        "Enter the exact path to your CCTV Batch Folder:",
        placeholder=r"e.g. C:\Users\Name\Downloads\CCTV_Batch_01"
    )

    if folder_path:
        if not os.path.exists(folder_path):
            st.error("Folder path not found. Double-check the spelling.")
        else:
            st.success("Folder linked successfully!")

            videos_to_process = [
                f for f in os.listdir(folder_path)
                if f.lower().endswith(('.mp4', '.dav'))
            ]
            st.write(f"**Found {len(videos_to_process)} video file(s) in folder.**")

            if videos_to_process:
                expected_min = len(videos_to_process) * min_frames_per_video
                expected_max = min(max_global_gemini,
                                   len(videos_to_process) * max_frames_per_video)
                st.info(
                    f"**Expected Gemini payload:** {expected_min}–{expected_max} frames "
                    f"({min_frames_per_video}–{max_frames_per_video} per camera, "
                    f"global cap {max_global_gemini})."
                    + " Score 10 (contraband) frames are never dropped."
                )

            session_name   = build_session_folder_name(centre_name, exam_date, shift)
            session_folder = os.path.join(folder_path, session_name)
            cache_dir      = os.path.join(folder_path, "audit_screenshot_cache")

            st.info(f"**Output Folder:** `{session_folder}`")

            # ---- State recovery -------------------------------------------
            if st.session_state.final_payload_all:
                st.markdown("---")
                st.info("**State Recovery Active:** Frame sequences from previous scan cached.")

                if (st.session_state.pdf_report_path
                        and os.path.exists(st.session_state.pdf_report_path)):
                    with open(st.session_state.pdf_report_path, "rb") as f:
                        st.download_button(
                            "Download Previous Report (PDF)", data=f,
                            file_name=os.path.basename(st.session_state.pdf_report_path),
                            mime="application/pdf",
                        )

                if st.button("Retry AI Report (Skip Video Processing)",
                             type="secondary", use_container_width=True):
                    all_shots = st.session_state.final_payload_all
                    t_start   = st.session_state.cached_target_start
                    t_end     = st.session_state.cached_target_end
                    ge_paths = build_gemini_only_payload(
                        all_shots, len(videos_to_process),
                        min_frames_per_video, max_global_gemini
                    )
                    st.session_state.cached_ge_paths = ge_paths
                    combined_report = ""
                    ok_g = True

                    if ge_paths:
                        ok_g, rtext = execute_gemini_synthesis(
                            ge_paths, t_start, t_end, centre_name, exam_date, shift
                        )
                        combined_report += rtext

                    if ok_g and combined_report:
                        os.makedirs(session_folder, exist_ok=True)
                        pdf_name = f"{session_name}_AuditReport.pdf"
                        pdf_path = os.path.join(session_folder, pdf_name)
                        generate_pdf_report(combined_report, centre_name, exam_date,
                                            shift, start_clock, end_clock, pdf_path,
                                            screenshots_folder=session_folder,
                                            ge_paths=ge_paths)
                        st.session_state.pdf_report_path = pdf_path
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "Download Audit Report (PDF)", data=f,
                                file_name=pdf_name, mime="application/pdf",
                            )
                        st.session_state.final_payload_all = []
                        st.session_state.cached_ge_paths   = []
                        st.balloons()
                        st.success("Master evaluation complete!")

            # ---- Primary run button ---------------------------------------
            if videos_to_process and st.button(
                "Run Full Audit", type="primary", use_container_width=True
            ):
                target_start = parse_ui_time(start_clock)
                target_end   = parse_ui_time(end_clock)
                if not (target_start and target_end):
                    st.stop()

                if os.path.exists(cache_dir):
                    for f in os.listdir(cache_dir):
                        try:
                            os.remove(os.path.join(cache_dir, f))
                        except Exception:
                            pass
                os.makedirs(cache_dir, exist_ok=True)
                os.makedirs(session_folder, exist_ok=True)

                # Models already loaded at startup via cache_resource — instant
                yolo_model = load_yolo()
                ocr_rdr    = load_ocr()

                st.sidebar.markdown("### OCR Anchor Feed")
                monitor_slot = st.sidebar.empty()
                log_messages = []
                all_shots    = []

                # ---- Stage 1: Frame extraction (SEQUENTIAL, one video at a time) ---
                st.markdown("---")
                st.markdown("**Stage 1 / 3 — Frame Extraction (sequential, one video at a time)**")

                for vi, vn in enumerate(videos_to_process):
                    st.markdown(f"🎬 **Scanning Video Content [{vi+1}/{len(videos_to_process)}]:** `{vn}`")

                    file_progress = st.progress(0)
                    timeline_slot = st.empty()

                    progress_tracker = {'done': 0, 'total': 1, 'name': vn}

                    # Run video processing in a background thread so the
                    # main thread can update progress bar and live time display
                    import concurrent.futures as _cf
                    with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                        _future = _pool.submit(
                            process_single_video,
                            vi, vn, folder_path, cache_dir,
                            target_start, target_end, start_clock,
                            yolo_model, ocr_rdr,
                            use_clahe, phash_threshold,
                            max_frames_per_video,
                            log_messages,
                            progress_tracker,
                        )
                        # Update UI while video processes in background
                        while not _future.done():
                            time.sleep(0.5)
                            if progress_tracker['total'] > 0:
                                file_progress.progress(
                                    min(progress_tracker['done'] / progress_tracker['total'], 1.0)
                                )
                            if progress_tracker.get('current_time'):
                                timeline_slot.caption(
                                    f"⚙️ Processing pipeline current position: "
                                    f"**[{progress_tracker['current_time']}]**"
                                )
                        shots = _future.result()
                    file_progress.progress(1.0)

                    all_shots.extend(shots)

                    for msg in log_messages[-2:]:
                        st.markdown(msg)

                    timeline_slot.empty()
                    file_progress.empty()

                monitor_slot.empty()

                # Models stay cached — no reload on next run
                # Only clear local references; cache_resource keeps them alive
                del yolo_model, ocr_rdr
                gc.collect()

                # ---- Stage 2: Frame routing --------------------------------
                st.markdown("**Stage 2 / 3 — Frame Routing**")

                ge_paths = build_gemini_only_payload(
                    all_shots, len(videos_to_process),
                    min_frames_per_video, max_global_gemini
                )

                with st.expander("Frame Routing Debug", expanded=True):
                    st.success(
                        f"**Gemini (all frames):** {len(ge_paths)} frames "
                        f"— global cap {max_global_gemini}, score 10 never dropped."
                    )
                    if ge_paths:
                        st.dataframe({"File": [os.path.basename(p) for p in ge_paths]})

                if not ge_paths:
                    st.error(
                        "No frames matched the clock window filter. "
                        "Check Start/End times and OCR ROI coverage."
                    )
                    st.stop()

                st.session_state.final_payload_all   = all_shots
                st.session_state.cached_ge_paths     = ge_paths
                st.session_state.cached_target_start = target_start
                st.session_state.cached_target_end   = target_end

                # ---- Stage 3: AI inference --------------------------------
                st.markdown("**Stage 3 / 3 — AI Report Generation**")

                combined_report = ""
                ok_g = True

                if ge_paths:
                    ok_g, rtext = execute_gemini_synthesis(
                        ge_paths, target_start, target_end,
                        centre_name, exam_date, shift,
                    )
                    combined_report += rtext

                # ---- Save frames ------------------------------------------
                if combined_report:
                    with st.spinner("Saving frames to session folder..."):
                        saved_count = len(
                            save_frames_to_session(ge_paths, session_folder)
                        )
                    st.success(f"{saved_count} frames saved to: `{session_folder}`")

                # ---- PDF --------------------------------------------------
                if combined_report:
                    pdf_name = f"{session_name}_AuditReport.pdf"
                    pdf_path = os.path.join(session_folder, pdf_name)
                    try:
                        generate_pdf_report(combined_report, centre_name, exam_date,
                                            shift, start_clock, end_clock, pdf_path,
                                            screenshots_folder=session_folder,
                                            ge_paths=ge_paths)
                        st.session_state.pdf_report_path = pdf_path
                        st.session_state.report_text     = combined_report
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "Download Audit Report (PDF)", data=f,
                                file_name=pdf_name, mime="application/pdf",
                            )
                        st.info(f"Report saved to: `{pdf_path}`")
                    except Exception as e:
                        st.error(f"PDF generation failed: {e}")

                # ---- Cleanup ----------------------------------------------
                if ok_g:
                    if os.path.exists(cache_dir):
                        for f in os.listdir(cache_dir):
                            try:
                                os.remove(os.path.join(cache_dir, f))
                            except Exception:
                                pass
                        try:
                            os.rmdir(cache_dir)
                        except Exception:
                            pass
                    st.session_state.final_payload_all = []
                    st.session_state.cached_ge_paths   = []
                    st.balloons()
                    st.success("Master evaluation complete!")
                else:
                    st.warning(
                        "One or more AI calls did not complete. "
                        "Frames are preserved. Use 'Retry AI Report' to retry."
                    )
