@echo off
title RENCORA - Build (EXE + Installer)
setlocal enabledelayedexpansion
cd /d "%~dp0"

where python >nul 2>&1 || (echo Python nicht gefunden. & pause & exit /b 1)

echo [1/4] Build-Werkzeuge installieren...
python -m pip install --upgrade pyinstaller >nul

echo [2/4] cloudflared beschaffen und verifizieren...
python tools\fetch_cloudflared.py || (echo cloudflared-Beschaffung fehlgeschlagen. & pause & exit /b 1)

echo [3/4] RENCORA.exe bauen...
python -m PyInstaller main.spec --noconfirm || (echo Build fehlgeschlagen. & pause & exit /b 1)

echo [4/4] Windows-Installer bauen...
set "ISCC="
for %%P in (
  "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do (if exist "%%~P" set "ISCC=%%~P")

if not defined ISCC (
    echo.
    echo RENCORA.exe fertig: dist\RENCORA\RENCORA.exe
    echo Inno Setup 6 nicht gefunden - kein Installer gebaut.
    echo Installieren mit:  winget install JRSoftware.InnoSetup
    pause & exit /b 0
)

"!ISCC!" installer\rencora.iss || (echo Installer-Build fehlgeschlagen. & pause & exit /b 1)

echo.
echo Fertig.
echo   App-Ordner:  dist\RENCORA\RENCORA.exe
echo   Installer:   installer\Output\RENCORA_Setup.exe
pause
