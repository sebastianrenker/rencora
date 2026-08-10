# Sicherheitsmodell und ehrliche Grenzen

RENCORA ist ein sicherheitsbewusst gebauter, lokal-first Assistent — aber kein
extern auditiertes Produktionssystem und nicht „unhackbar". Dieses Dokument nennt
die Schutzmaßnahmen und die bekannten Grenzen offen.

## 1. Geheimnisse im Ruhezustand

Der Gemini-Schlüssel wird nicht im Klartext gespeichert. Beim ersten Start wird er
mit der Windows Data Protection API (DPAPI, `CryptProtectData`) verschlüsselt und an
das Windows-Benutzerkonto gebunden; der Klartext wird aus der Konfiguration entfernt.
Ein kopierter Konfigurations-Blob lässt sich auf einem anderen Rechner oder unter
einem anderen Konto nicht entschlüsseln. Der Schlüssel liegt zu keinem Zeitpunkt im
Repository oder in der ausführbaren Datei.

## 2. Fernsteuerung (Smartphone-Dashboard)

- Nutzlast Ende-zu-Ende mit AES-256-GCM verschlüsselt (authentifizierte
  Verschlüsselung über die native WebCrypto-API des Browsers).
- Zugriff nur mit gültigem Sitzungsschlüssel; danach zeitlich begrenzte Auth-Token
  mit Leerlauf-Ablauf.
- Login-Rate-Limiting mit Sperre nach wenigen Fehlversuchen, gebunden an die echte
  TCP-Peer-Adresse. Der `X-Forwarded-For`-Header wird nicht vertraut.
- Die eingehende Firewallregel für den LAN-Zugriff ist auf das lokale Subnetz und
  das private Netzwerkprofil beschränkt — erreichbar nur für Geräte im selben Netz
  (z. B. das eigene Handy), nicht für beliebige entfernte Hosts. Ein als
  „Öffentlich" eingestuftes Netzwerk wird **nicht** automatisch auf „Privat"
  herabgestuft (`allow_network_profile_change`, Standard aus); die gesamte
  Firewalländerung lässt sich abschalten (`lan_firewall`).
- Der optionale Internet-Tunnel nutzt eine fest gepinnte cloudflared-Version. Die
  Binärdatei wird vor jeder Nutzung gegen eine bekannte SHA-256-Prüfsumme
  verifiziert; eine abweichende oder untergeschobene Datei wird verworfen statt
  ausgeführt (Supply-Chain-Schutz).

## 3. Gemini / Google — welche Daten verarbeitet werden

Solange die Sprach-/Standardantwort über Gemini läuft, werden die dafür nötigen
Eingaben (Audio, ggf. Bildschirm-/Kamerabilder, Text) zur Verarbeitung an Google
übertragen. Das lässt sich bei Nutzung von Gemini technisch nicht vermeiden.
Maßnahmen zur Datensparsamkeit:

- **Kostenpflichtiger API-Zugang verwenden.** Für die kostenpflichtige Gemini-API
  nutzt Google die übermittelten Inhalte laut eigenen Bedingungen nicht zum Training
  und speichert sie nicht dauerhaft. Der kostenlose Tarif kann Inhalte auswerten —
  für private Daten daher einen abrechenbaren Schlüssel verwenden.
- **Vollständig lokaler Betrieb.** Für Text- und Agentenantworten lässt sich das
  eigene Modell (RencoraLM v3) oder Ollama wählen; dann verlässt für diese Antworten
  nichts den Rechner. Wer Google ganz vermeiden will, nutzt den lokalen Modus und
  verzichtet auf die Gemini-Sprachschicht.
- Es werden keine Inhalte zusätzlich an Dritte gesendet; der Schlüssel bleibt lokal
  und DPAPI-geschützt (Abschnitt 1).

## 4. Generierter Automatisierungscode

Von Gemini generierter Automatisierungscode wird vor der Ausführung strukturell
geprüft: eine AST-Analyse blockiert Importe, Dunder-Zugriffe und gefährliche
Aufrufe (`eval`, `exec`, `os`/`sys`/`subprocess`, Prozessstart) unabhängig von der
Schreibweise, und die Ausführung läuft mit stark eingeschränkten Builtins. Nicht
parsebarer Code gilt als unsicher. Die Aktion selbst ist zusätzlich als
risikoreich eingestuft und erfordert eine Bestätigung (Abschnitt 5).

## 5. Vertrauensgrenze für externe Inhalte

Anweisungen kommen ausschließlich vom Nutzer im Gespräch. Alle über Werkzeuge
gelesenen Inhalte — Webseiten, Dateien, E-Mails, importierte Chats, OCR-Text —
gelten als Daten, niemals als Anweisungen. Diese Grenze ist im System-Prompt fest
verankert; Ergebnisse extern beeinflusster Werkzeuge werden zusätzlich als
untrusted markiert, bevor sie an das Modell zurückgehen. So kann in fremden
Inhalten eingebetteter Text keine privilegierten Aktionen auslösen
(Prompt-Injection-Schutz).

Risikoreiche Aktionen (z. B. Nachrichten senden, Kalender/E-Mail, System- und
Desktop-Steuerung) sind mit Risikostufen versehen und erfordern eine
ausdrückliche Bestätigung; ohne Bestätigung werden sie verweigert (sicherer
Standard).

## 6. Abhängigkeiten

`requirements.txt` ist auf feste Versionen gepinnt (reproduzierbare Installation).
Vor einem Update empfiehlt sich ein Blick auf die jeweiligen Sicherheitshinweise.

## 7. Bekannte Grenzen

- Absolute Sicherheit gibt es nicht; die Software wird ohne Gewährleistung
  bereitgestellt (siehe `LICENSE`).
- Die ausführbare Datei ist nicht code-signiert: Windows SmartScreen warnt bei
  unbekannten .exe, und Virenscanner können bei PyInstaller-Dateien Fehlalarme
  auslösen. Abhilfe schafft nur eine erworbene Code-Signatur.
- Die optionale Globus-Ansicht im Dashboard lädt eine 3D-Bibliothek und Schriften
  von einem CDN. Der Sicherheitspfad (Verschlüsselung, Authentifizierung) ist davon
  unabhängig; für maximale Datensparsamkeit lassen sich diese Ressourcen lokal
  einbinden.

## 8. Schwachstellen melden

Sicherheitsprobleme bitte nicht öffentlich als Issue melden, sondern über die private
Sicherheitsmeldung von GitHub (Repository → Security → Report a vulnerability).
