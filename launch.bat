@echo off
setlocal
cd /d "%~dp0"
title PDF Tool - Startup
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import pymupdf, tkinter" >nul 2>&1
  if not errorlevel 1 goto :use_py
)
where python >nul 2>&1
if not errorlevel 1 (
  python -c "import pymupdf, tkinter" >nul 2>&1
  if not errorlevel 1 goto :use_python
)
echo PDF Tool could not find Python with PyMuPDF and tkinter.
echo.
echo Try running install.bat first.
echo If the problem continues, run diagnose.bat and check the output.
pause
exit /b 1
:use_py
py -3 "%~dp0pdf_tool.py"
if errorlevel 1 goto :failure
exit /b 0
:use_python
python "%~dp0pdf_tool.py"
if errorlevel 1 goto :failure
exit /b 0
:failure
echo.
echo PDF Tool stopped with an error. Please take a screenshot of the message above.
pause
exit /b 1
