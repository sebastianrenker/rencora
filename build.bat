@echo off
title RENCORA v7 - Build
setlocal
cd /d "%~dp0"

where python >nul 2>&1 || (echo Python nicht gefunden. & pause & exit /b 1)

echo Installiere Build-Werkzeuge...
python -m pip install --upgrade pyinstaller >nul

echo Baue RENCORA.exe...
pyinstaller main.spec --noconfirm || (echo Build fehlgeschlagen. & pause & exit /b 1)

echo.
echo Fertig. Ergebnis: dist\RENCORA\RENCORA.exe
pause
