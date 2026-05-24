@echo off
REM Build Windows executable with PyInstaller
REM Requires: pip install pyinstaller pillow

echo Building FapForge for Windows...
pyinstaller --onefile --console --icon=FapForge.ico --name FapForge fap_builder.py
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
echo Done! Executable at: dist\FapForge.exe
