@echo off
title RENCORA v7 - Installation
setlocal
cd /d "%~dp0"

where python >nul 2>&1 || (
    echo Python 3.11 oder 3.12 wird benoetigt und wurde nicht gefunden.
    echo Download: https://www.python.org/downloads/
    pause & exit /b 1
)

echo [1/4] pip aktualisieren...
python -m pip install --upgrade pip >nul

echo [2/4] Abhaengigkeiten installieren...
python -m pip install -r requirements.txt || (
    echo Installation der Abhaengigkeiten fehlgeschlagen.
    pause & exit /b 1
)

echo [3/4] Playwright-Browser installieren...
python -m playwright install >nul

echo [4/4] Konfiguration vorbereiten...
if not exist "config\api_keys.json" (
    copy "config_example\api_keys.json" "config\api_keys.json" >nul
    echo Konfiguration angelegt: config\api_keys.json
)

echo.
echo Installation abgeschlossen.
echo Traege deinen Gemini-Schluessel in config\api_keys.json ein und starte START_RENCORA.bat
pause
