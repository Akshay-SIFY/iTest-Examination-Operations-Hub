#!/usr/bin/env python3
"""
iTest Video Tools Hub — Desktop Shortcut Creator
Double-click this file once to create the shortcut on your Desktop.
Akshay Singh | iTest Content Team | SIFY Technologies
"""

import os
import sys
import subprocess
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    print("=" * 55)
    print("  iTest Video Tools Hub — Shortcut Creator")
    print("  Akshay Singh | iTest Content Team | SIFY Technologies")
    print("=" * 55)
    print()

    # This script's directory = VideoToolsHub folder
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path  = os.path.join(base_dir, "START HUB.bat")
    desktop   = os.path.join(os.path.expanduser("~"), "Desktop")
    lnk_path  = os.path.join(desktop, "iTest Video Tools Hub.lnk")

    # Verify bat exists
    if not os.path.exists(bat_path):
        print(f"  [ERROR] Cannot find: {bat_path}")
        print("  Make sure this script is inside the VideoToolsHub folder.")
        input("\n  Press Enter to exit...")
        return

    # Try win32com first (most reliable)
    try:
        from win32com.client import Dispatch
        shell    = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        shortcut.Targetpath       = bat_path
        shortcut.WorkingDirectory = base_dir
        shortcut.Description      = "iTest Video Tools Hub"
        shortcut.WindowStyle      = 1
        shortcut.save()
        print(f"  Shortcut created via win32com.")
        _success(lnk_path)
        return
    except ImportError:
        print("  win32com not found, trying to install pywin32...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "pywin32", "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            from win32com.client import Dispatch
            shell    = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(lnk_path)
            shortcut.Targetpath       = bat_path
            shortcut.WorkingDirectory = base_dir
            shortcut.Description      = "iTest Video Tools Hub"
            shortcut.WindowStyle      = 1
            shortcut.save()
            print("  pywin32 installed and shortcut created.")
            _success(lnk_path)
            return
        except Exception as e:
            print(f"  win32com failed: {e}")

    # Fallback: VBScript
    try:
        vbs = os.path.join(os.environ.get("TEMP", base_dir), "mk_lnk.vbs")
        with open(vbs, "w") as f:
            f.write(f'Set oWS = WScript.CreateObject("WScript.Shell")\n')
            f.write(f'Set oLink = oWS.CreateShortcut("{lnk_path}")\n')
            f.write(f'oLink.TargetPath = "{bat_path}"\n')
            f.write(f'oLink.WorkingDirectory = "{base_dir}"\n')
            f.write(f'oLink.Description = "iTest Video Tools Hub"\n')
            f.write(f'oLink.WindowStyle = 1\n')
            f.write(f'oLink.Save\n')
        result = subprocess.run(["cscript", "//nologo", vbs],
                                capture_output=True, text=True)
        os.remove(vbs)
        if os.path.exists(lnk_path):
            print("  Shortcut created via VBScript.")
            _success(lnk_path)
            return
        else:
            print(f"  VBScript ran but shortcut not found. Error: {result.stderr}")
    except Exception as e:
        print(f"  VBScript fallback failed: {e}")

    # Last fallback: .url file (always works, no admin needed)
    try:
        url_path = os.path.join(desktop, "iTest Video Tools Hub.url")
        with open(url_path, "w") as f:
            f.write("[InternetShortcut]\n")
            f.write(f"URL=file:///{bat_path.replace(os.sep, '/')}\n")
            f.write(f"WorkingDirectory={base_dir}\n")
        print("  Created .url shortcut on Desktop (fallback method).")
        print(f"  Location: {url_path}")
        input("\n  Press Enter to exit...")
    except Exception as e:
        print(f"\n  [ERROR] All methods failed: {e}")
        print("\n  MANUAL OPTION:")
        print(f"  Right-click 'START HUB.bat' → Send to → Desktop (create shortcut)")
        input("\n  Press Enter to exit...")


def _success(lnk_path):
    print(f"\n  SUCCESS!")
    print(f"  Shortcut: {lnk_path}")
    print(f"\n  You can now double-click 'iTest Video Tools Hub'")
    print(f"  on your Desktop to launch the Hub anytime.")
    input("\n  Press Enter to exit...")


if __name__ == "__main__":
    main()
