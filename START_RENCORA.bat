@echo off
title RENCORA v7 - Renker Industries
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] RENCORA wurde unerwartet beendet.
    pause
)
