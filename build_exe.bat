@echo off
cd /d "%~dp0"
py -m pip install --upgrade pymupdf pyinstaller
if errorlevel 1 goto :fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --name PDF_Tool pdf_tool.py
if errorlevel 1 goto :fail
echo EXE created in dist folder.
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
