@echo off
REM RencoraLM v3 als lokalen Server starten (Port 5151), dann im UI unter
REM Einstellungen -> Modell "RencoraLM v3" waehlen. Fenster schliessen zum Stoppen.
setlocal
python "%~dp0tools\rencora_lm_server.py" --port 5151
pause
