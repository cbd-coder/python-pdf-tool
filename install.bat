@echo off
setlocal
cd /d "%~dp0"
title PDF Tool - Install
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m pip install --upgrade pymupdf
  goto :end
)
where python >nul 2>&1
if not errorlevel 1 (
  python -m pip install --upgrade pymupdf
  goto :end
)
echo Python was not found. Please install Python first or check PATH.
:end
if errorlevel 1 echo Installation failed - see the message above.
pause
