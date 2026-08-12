# RENCORA v7

Persönlicher Desktop-KI-Assistent von Renker Industries für Windows, macOS und Linux.
RENCORA verbindet Echtzeit-Sprache, Bildschirm- und Kamera-Wahrnehmung, Systemsteuerung
und persistentes Gedächtnis in einer nativen PyQt6-Oberfläche.

Sicherheitsbewusst gebaut, aber kein extern auditiertes Produktionssystem. Sicherheits-
modell, Datenschutz und bekannte Grenzen: [SECURITY.md](SECURITY.md).

## Funktionen

- Echtzeit-Sprachdialog (Gemini Live API)
- Systemsteuerung: Anwendungen, Dateien, Terminalbefehle
- Bildschirm- und Webcam-Analyse
- Mehrstufige Aufgabenplanung über Agenten
- Persistentes Gedächtnis
- Fernsteuerung per Smartphone über verschlüsselten Tunnel
- Wählbares Text-/Agentenmodell: lokales Ollama oder das eigene RencoraLM v3

## Voraussetzungen

- Windows 10/11, macOS oder Linux
- Python 3.11 oder 3.12
- Mikrofon
- Gemini API-Schlüssel

## Installation

```bat
git clone https://github.com/sebastianrenker/rencora.git
cd rencora
install.bat
```

Anschließend `config/api_keys.json` öffnen und `gemini_api_key` eintragen.

Manuell (alle Plattformen):

```bash
pip install -r requirements.txt
playwright install
cp config_example/api_keys.json config/api_keys.json
```

## Start

```bash
python main.py
```

Unter Windows alternativ `START_RENCORA.bat`.

## Ausführbare Datei (.exe)

Lokal bauen (Windows, erzeugt `dist/RENCORA/RENCORA.exe`):

```bat
build.bat
```

Alternativ baut die GitHub-Action die .exe automatisch und stellt sie unter „Actions"
als Download bereit.

## Sicherheit & Datenschutz

- Der Gemini-Schlüssel wird per Windows DPAPI verschlüsselt gespeichert (an das
  Benutzerkonto gebunden), nie im Klartext, nie im Repository oder in der .exe.
- Für vollständig lokalen Betrieb ohne Google lässt sich als Text-/Agentenmodell
  das eigene RencoraLM v3 oder Ollama wählen.
- Details, Bedrohungsmodell und Grenzen: [SECURITY.md](SECURITY.md).

## RENKER-Plattform

Rencora ist die **ACT**-Säule der Renker-Plattform — Infrastruktur für
vertrauenswürdige, autonome KI-Systeme. Gesamtarchitektur und die anderen
Säulen: [RENKER_PLATFORM.md](RENKER_PLATFORM.md).

```text
RENKER — ACT (Rencora) · LEARN (Continuum) · SECURE (RenkerVault)
                         gemeinsames Fundament: renker-core
```

| Säule | Rolle | Repo |
| --- | --- | --- |
| Continuum | LEARN | https://github.com/sebastianrenker/continuum |
| RenkerVault | SECURE | https://github.com/sebastianrenker/renkervault |
| renker-core-authz | öffentlicher Authorization-Core (von Rencora optional konsumiert) | https://github.com/sebastianrenker/renker-core-authz |

## Lizenz

Nur für persönliche, nicht-kommerzielle Nutzung. © Renker Industries.
