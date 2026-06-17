# iTest Video Tools Hub
### Akshay Singh | iTest Content Team | SIFY Technologies

---

## Folder Structure

Place ALL files like this — nothing else needed:

```
VideoToolsHub/
│
├── START HUB.bat          ← Double-click to launch (Windows)
├── launcher.py            ← Main Hub UI
├── README.txt             ← This file
│
└── tools/
    ├── cctv_analyser.py   ← YOUR existing CCTV Analyser (copy here)
    ├── dav_converter.py   ← DAV → MP4 Converter (provided)
    └── mp4_merger.py      ← MP4 Merger (provided)
```

---

## Setup (One Time)

1. Install Python 3.9+ → https://www.python.org/downloads/
   ✔ Check "Add Python to PATH" during install

2. Install your existing dependencies (same as before):
   ```
   pip install streamlit flask
   ```

3. Copy your existing CCTV Analyser app.py into the tools/ folder
   and rename it:  cctv_analyser.py

---

## How to Start

**Double-click:  START HUB.bat**

The Hub will:
- Open the Launcher window with all 3 tool cards
- Let you click ▶ Launch on any tool independently
- Tools run as separate processes — fully isolated
- Web tools (CCTV Analyser, DAV Converter) auto-open in your browser
- MP4 Merger opens as a desktop window

---

## Running Tools Simultaneously

All 3 tools run as independent processes.
You can have all 3 running at the same time — they don't interfere.

For the CCTV Analyser (Streamlit), open as many browser tabs as you want:
→ Each tab is a separate session
→ Duplicate the tab in Chrome/Edge — works exactly like before

---

## Ports Used

| Tool             | Type      | Port  | URL                     |
|------------------|-----------|-------|-------------------------|
| CCTV Analyser    | Streamlit | 8501  | http://localhost:8501   |
| DAV Converter    | Flask     | 5001  | http://localhost:5001   |
| MP4 Merger       | Tkinter   | —     | Desktop window          |

---

## No Logic Changes

The processing logic in all 3 tools is 100% identical to your originals.
Only the visual theme was updated to match the Hub design.

---

*iTest Video Tools Hub · SIFY Technologies · 2026*
