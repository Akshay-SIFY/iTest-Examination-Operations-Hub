@echo off
setlocal EnableDelayedExpansion
title Centralized Examination Operations Platform — Deployer

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

echo ============================================================
echo  Automated Installer & Launch Engine v2.5
echo  SIFY Technologies ^| Centralized Exam Ops Platform
echo ============================================================
echo.

:: 1. Force administration context shift if required for shortcuts
set "VENV_DIR=%DIR%\.venv"

:: 2. Find or Install Python Runtime
where python >nul 2>&1
if errorlevel 1 (
    if not exist "%DIR%\python_installer.exe" (
        echo [LAUNCH] Runtime missing. Downloading Python 3.11 core binaries...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%DIR%\python_installer.exe'"
    )
    echo [SYSTEM] Running silent background Python configuration. Please wait...
    start /wait "" "%DIR%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del "%DIR%\python_installer.exe"
    
    :: Refresh Path variables instantly
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\;%LOCALAPPDATA%\Programs\Python\Python311\Scripts\;%PATH%"
)

:: 3. Setup Dedicated Virtual Environment
if not exist "%VENV_DIR%" (
    echo [SYSTEM] Provisioning isolated execution container (.venv)...
    python -m venv "%VENV_DIR%"
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"

:: 4. Verify System Core Upgrades
echo [SYSTEM] Evaluating package integrity states...
%PIP_EXE% install --upgrade pip -q

:: 5. Install Required Package Extensions
echo [DEPENDENCY] Confirming dependencies matrix...
%PYTHON_EXE% -c "import streamlit" >nul 2>&1 || (echo Installing streamlit... & %PIP_EXE% install streamlit -q)
%PYTHON_EXE% -c "import google.generativeai" >nul 2>&1 || (echo Installing google-generativeai... & %PIP_EXE% install google-generativeai -q)
%PYTHON_EXE% -c "import openpyxl" >nul 2>&1 || (echo Installing openpyxl... & %PIP_EXE% install openpyxl -q)
%PYTHON_EXE% -c "import pandas" >nul 2>&1 || (echo Installing pandas... & %PIP_EXE% install pandas -q)
%PYTHON_EXE% -c "import rapidfuzz" >nul 2>&1 || (echo Installing rapidfuzz... & %PIP_EXE% install rapidfuzz -q)
%PYTHON_EXE% -c "import requests" >nul 2>&1 || (echo Installing network extensions... & %PIP_EXE% install requests -q)
%PYTHON_EXE% -c "import PIL" >nul 2>&1 || (echo Installing imaging frameworks... & %PIP_EXE% install pillow -q)

:: 6. Auto-Create Shortcut on Initial Build
if not exist "%userprofile%\Desktop\iTest Video Tools Hub.lnk" (
    if not exist "%userprofile%\Desktop\iTest Video Tools Hub.url" (
        echo [DESKTOP] Injecting primary system shortcut hook...
        "%PYTHON_EXE%" "%DIR%\Create Desktop Shortcut.py"
    )
)

:: 7. Hand over operational authority to Launcher
echo.
echo [LAUNCH] Starting Platform Environment UI...
"%PYTHON_EXE%" "%DIR%\launcher.py"

if %errorlevel% equ 999 (
    echo.
    echo ============================================================
    echo  [REBOOT] System updated successfully. Recalibrating state...
    echo ============================================================
    timeout /t 3
    goto :Launch
)

if errorlevel 1 (
    echo.
    echo ============================================================
    echo  Platform execution error caught. Review debug metrics above.
    echo ============================================================
    pause
)
exit /b