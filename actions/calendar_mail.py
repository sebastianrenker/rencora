"""
actions/calendar_mail.py

NEUE DATEI - Kalender- und E-Mail-Zugriff fuer RENCORA (Google Calendar +
Gmail API). Schliesst die fehlende "Was steht heute an / lies mir die
wichtigen Mails vor"-Luecke.

Warum Google APIs statt z.B. Outlook-COM: Sebastian nutzt laut den
bisherigen Modulen (flight_finder, browser_control) bereits viel
Web-zentrierte Automatisierung; Google Calendar/Gmail laufen
plattformunabhaengig (Windows/macOS/Linux) ueber dieselbe REST-API,
waehrend Outlook-COM nur unter Windows mit installiertem Outlook
funktioniert. Falls du stattdessen lokales Outlook willst, sag
Bescheid - das waere ein separates drop-in Modul mit identischer
oeffentlicher Funktionssignatur (calendar_mail(parameters, player) /
get_upcoming_events() / get_unread_important_mail()), austauschbar ohne
main.py oder proactive_engine.py anzufassen.

SETUP (einmalig):
1. https://console.cloud.google.com -> neues Projekt -> "Google
   Calendar API" und "Gmail API" aktivieren.
2. OAuth-Client-ID erstellen (Typ "Desktop App"), JSON herunterladen,
   speichern unter: config/google_oauth_client.json
3. pip install google-auth-oauthlib google-api-python-client
4. Beim ersten Aufruf eines Kalender/Mail-Tools oeffnet sich einmalig
   ein Browserfenster zur Anmeldung; danach liegt ein Token unter
   ~/.rencora/google_token.json und der Login wird automatisch erneuert.

TOOL-DECLARATION (main.py TOOL_DECLARATIONS, siehe PATCH_main.py.txt):
    {
        "name": "calendar_mail",
        "description": (
            "Manages calendar events and email. Use for: checking today's "
            "schedule, upcoming events, creating/moving/cancelling calendar "
            "events, reading or summarizing recent emails, checking unread "
            "or important mail. ONLY tool for calendar and email requests."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": (
                    "agenda_today | agenda_range | create_event | move_event | "
                    "cancel_event | list_unread_mail | summarize_mail | search_mail"
                )},
                "title":        {"type": "STRING", "description": "Event title / mail search query"},
                "date":         {"type": "STRING", "description": "Date YYYY-MM-DD"},
                "time":         {"type": "STRING", "description": "Time HH:MM (24h)"},
                "duration_min": {"type": "INTEGER", "description": "Event duration in minutes (default 60)"},
                "days_ahead":   {"type": "INTEGER", "description": "How many days ahead for agenda_range"},
                "event_id":     {"type": "STRING", "description": "Event id for move_event/cancel_event"},
                "max_results":  {"type": "INTEGER", "description": "Max emails to return (default 5)"},
            },
            "required": ["action"]
        }
    }

DISPATCH (main.py _execute_tool, siehe PATCH_main.py.txt):
    elif name == "calendar_mail":
        r = await loop.run_in_executor(None, lambda: calendar_mail(parameters=args, player=self.ui))
        result = r or "Done."
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _token_path() -> Path:
    d = Path.home() / ".rencora"
    d.mkdir(parents=True, exist_ok=True)
    return d / "google_token.json"


def _client_secret_path() -> Path:
    return _base_dir() / "config" / "google_oauth_client.json"


def _get_credentials():
    """
    Laedt/erneuert die OAuth-Credentials. Wirft eine sprechende
    Exception, wenn die Einrichtung fehlt - der Caller faengt das ab
    und gibt dem Nutzer eine klare Anleitung statt einem Traceback.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    token_path = _token_path()

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        secret_path = _client_secret_path()
        if not secret_path.exists():
            raise RuntimeError(
                "Google Calendar/Mail isn't set up yet. Save your OAuth client "
                "JSON to config/google_oauth_client.json first."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _calendar_service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=_get_credentials())


def _gmail_service():
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=_get_credentials())


def _humanize_delta(target: datetime) -> str:
    delta = target - datetime.now(target.tzinfo)
    minutes = int(delta.total_seconds() // 60)
    if minutes <= 0:
        return "now"
    if minutes < 60:
        return f"in {minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    return f"in {hours} hour{'s' if hours != 1 else ''}"


def get_upcoming_events(within_minutes: int = 10) -> list[dict]:
    """
    Liefert Kalendertermine, die innerhalb von `within_minutes` Minuten
    beginnen. Gibt bei fehlender Konfiguration/Fehler eine leere Liste
    zurueck (nie eine Exception) - das ist die Erwartung von
    proactive_engine.check_upcoming_calendar_event.
    """
    try:
        service = _calendar_service()
    except Exception:
        return []

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(minutes=within_minutes)).isoformat() + "Z"

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception:
        return []

    events = []
    for item in result.get("items", []):
        start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
        if not start_raw:
            continue
        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            human = _humanize_delta(start_dt)
        except Exception:
            human = "soon"
        events.append({
            "id": item.get("id"),
            "summary": item.get("summary", "Untitled event"),
            "start_human": human,
        })
    return events


def get_unread_important_mail() -> list[dict]:
    """Liefert ungelesene, von Gmail als wichtig markierte Mails. Leere Liste statt Exception bei Fehler."""
    try:
        service = _gmail_service()
    except Exception:
        return []

    try:
        result = service.users().messages().list(
            userId="me",
            q="is:unread is:important",
            maxResults=5,
        ).execute()
    except Exception:
        return []

    mails = []
    for msg_ref in result.get("messages", []):
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
        except Exception:
            continue
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        mails.append({
            "id": msg_ref["id"],
            "from": headers.get("From", "unknown"),
            "subject": headers.get("Subject", "(no subject)"),
        })
    return mails


def _action_agenda(date_str: Optional[str], days_ahead: int) -> str:
    service = _calendar_service()

    if date_str:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        base = datetime.now()

    time_min = base.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    time_max = (base + timedelta(days=max(days_ahead, 1))).replace(
        hour=23, minute=59, second=59
    ).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    items = result.get("items", [])
    if not items:
        return "Nothing on the calendar for that period."

    lines = []
    for item in items:
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            when = dt.strftime("%a %H:%M")
        except Exception:
            when = start
        lines.append(f"{when} — {item.get('summary', 'Untitled')}")

    return "Here's what's coming up: " + "; ".join(lines)


def _action_create_event(title: str, date_str: str, time_str: str, duration_min: int) -> str:
    service = _calendar_service()

    start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duration_min or 60)

    event_body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Berlin"},
    }
    created = service.events().insert(calendarId="primary", body=event_body).execute()
    return f"Created \"{title}\" on {start_dt.strftime('%B %d at %H:%M')}."


def _action_move_event(event_id: str, date_str: str, time_str: str) -> str:
    service = _calendar_service()
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    duration = None
    old_start = event.get("start", {}).get("dateTime")
    old_end = event.get("end", {}).get("dateTime")
    if old_start and old_end:
        duration = datetime.fromisoformat(old_end) - datetime.fromisoformat(old_start)

    new_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    new_end = new_start + (duration or timedelta(hours=1))

    event["start"] = {"dateTime": new_start.isoformat(), "timeZone": "Europe/Berlin"}
    event["end"] = {"dateTime": new_end.isoformat(), "timeZone": "Europe/Berlin"}
    service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
    return f"Moved to {new_start.strftime('%B %d at %H:%M')}."


def _action_cancel_event(event_id: str) -> str:
    service = _calendar_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return "Event cancelled."


def _action_list_unread(max_results: int) -> str:
    mails = get_unread_important_mail()
    if not mails:
        return "No unread important mail."
    lines = [f"{m['from']}: {m['subject']}" for m in mails[:max_results or 5]]
    return "Unread and important: " + "; ".join(lines)


def _action_search_mail(query: str, max_results: int) -> str:
    service = _gmail_service()
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results or 5
    ).execute()
    msg_refs = result.get("messages", [])
    if not msg_refs:
        return f"No emails found for \"{query}\"."

    lines = []
    for ref in msg_refs:
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        lines.append(f"{headers.get('From', '?')}: {headers.get('Subject', '(no subject)')}")
    return f"Found {len(lines)} for \"{query}\": " + "; ".join(lines)


def calendar_mail(parameters: dict, player=None, response=None, session_memory=None) -> str:
    action = (parameters.get("action") or "").strip()

    try:
        if action == "agenda_today":
            return _action_agenda(None, days_ahead=1)
        elif action == "agenda_range":
            return _action_agenda(parameters.get("date"), parameters.get("days_ahead", 1))
        elif action == "create_event":
            title = parameters.get("title", "Untitled event")
            date_str = parameters.get("date", "")
            time_str = parameters.get("time", "")
            if not date_str or not time_str:
                return "I need both a date and a time to create that event."
            return _action_create_event(title, date_str, time_str, parameters.get("duration_min", 60))
        elif action == "move_event":
            event_id = parameters.get("event_id", "")
            if not event_id:
                return "I need the event id to move it — try asking me to find it first."
            return _action_move_event(event_id, parameters.get("date", ""), parameters.get("time", ""))
        elif action == "cancel_event":
            event_id = parameters.get("event_id", "")
            if not event_id:
                return "I need the event id to cancel it."
            return _action_cancel_event(event_id)
        elif action == "list_unread_mail":
            return _action_list_unread(parameters.get("max_results", 5))
        elif action in ("search_mail", "summarize_mail"):
            query = parameters.get("title") or parameters.get("query") or ""
            if not query:
                return "What should I search your mail for?"
            return _action_search_mail(query, parameters.get("max_results", 5))
        else:
            return f"Unknown calendar/mail action: {action}"

    except RuntimeError as e:
        if player:
            player.write_log(f"[calendar_mail]  {e}")
        return str(e)
    except Exception as e:
        if player:
            player.write_log(f"[calendar_mail]  {e}")
        return f"Calendar/mail request failed: {e}"
