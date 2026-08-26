@echo off
setlocal
cd /d "%~dp0"
title Texture Forge

echo.
echo   Texture Forge
echo   ----------------------------------------
echo.

REM ---- find a usable Python -------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (where python >nul 2>&1 && set "PY=python")

if not defined PY (
  echo   Python is not installed.
  echo.
  echo   Get it from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add Python to PATH" in the installer.
  echo.
  pause
  exit /b 1
)

REM ---- private venv, so nothing touches the system Python -------------------
if not exist ".venv\Scripts\python.exe" (
  echo   First run - creating a private Python environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo.
    echo   Could not create the environment. Is Python installed correctly?
    pause
    exit /b 1
  )
)

set "VPY=.venv\Scripts\python.exe"

REM Marker file rather than reinstalling every launch - pip is slow enough that
REM a few seconds on every start is noticeable.
if not exist ".venv\.deps-ok" (
  echo   Installing dependencies, one moment...
  "%VPY%" -m pip install --quiet --upgrade pip
  "%VPY%" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   Dependency install failed. Check your internet connection.
    pause
    exit /b 1
  )
  echo done > ".venv\.deps-ok"
)

echo   Starting...
echo.
echo   Texture Forge will open in your browser.
echo   Leave this window open while you use it - closing it stops the app.
echo.

REM Give the server a beat to bind before the browser asks for the page.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:4796"

"%VPY%" app.py

echo.
echo   Texture Forge has stopped.
pause
