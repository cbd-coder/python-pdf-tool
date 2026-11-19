@echo off
setlocal
cd /d "%~dp0"
title PDF Tool - Diagnostics
echo ==== PDF Tool Diagnostics ====
echo Folder: %cd%
echo.
echo [1] Python launchers:
where py 2>&1
where python 2>&1
echo.
echo [2] py version:
py -3 --version 2>&1
echo.
echo [3] Python version:
python --version 2>&1
echo.
echo [4] Import check via py:
py -3 -c "import sys; print(sys.executable); import pymupdf; print('PyMuPDF OK'); import tkinter; print('tkinter OK')" 2>&1
echo.
echo [5] Import check via python:
python -c "import sys; print(sys.executable); import pymupdf; print('PyMuPDF OK'); import tkinter; print('tkinter OK')" 2>&1
echo.
echo ==== Diagnostics finished ====
pause
