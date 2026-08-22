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

- Windows 10/11 (Installer) — macOS/Linux über den Quellcode-Weg
- Mikrofon
- Gemini API-Schlüssel (kostenlos, Link im Setup)
- Nur für den Quellcode-Weg: Python 3.11 oder 3.12

## Installation (Windows)

Fertigen Installer herunterladen und ausführen — kein Python nötig:

1. **[RENCORA_Setup.exe herunterladen](https://github.com/sebastianrenker/rencora/releases/latest)**
2. Doppelklick, dem Assistenten folgen.
3. Beim ersten Start den Gemini-Schlüssel eintragen. Den Schlüssel gibt es
   kostenlos über den anklickbaren Link direkt im Setup-Fenster
   ([Google AI Studio](https://aistudio.google.com/app/apikey)).

## Aus Quellcode (Entwickler)

```bat
git clone https://github.com/sebastianrenker/rencora.git
cd rencora
install.bat
python main.py
```

Alle Plattformen: `pip install -r requirements.txt`, `playwright install`,
`python main.py`.

## Selbst bauen

Erzeugt App-Ordner **und** den Windows-Installer `installer/Output/RENCORA_Setup.exe`
(benötigt [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```bat
build.bat
```

Auf einen Git-Tag `v*` baut die GitHub-Action den Installer automatisch und hängt
ihn an das Release an.

## Sicherheit & Datenschutz

- Der Gemini-Schlüssel wird per Windows DPAPI verschlüsselt gespeichert (an das
  Benutzerkonto gebunden), nie im Klartext, nie im Repository oder in der .exe.
- Für vollständig lokalen Betrieb ohne Google lässt sich als Text-/Agentenmodell
  das eigene RencoraLM v3 oder Ollama wählen.
- Details, Bedrohungsmodell und Grenzen: [SECURITY.md](SECURITY.md).

## Lizenz

Nur für persönliche, nicht-kommerzielle Nutzung. © Renker Industries.
