"""
whatsapp_import.py — RENCORA WhatsApp Chat Importer

Reads a WhatsApp chat export (.txt, exported via "Export chat" -> "Without
media"), figures out who took part, and stores EVERY message each person
ever sent — verbatim, in full, nothing filtered or summarized away — into
memory/people.json. A short compact recap per person is generated alongside
purely so something reasonably sized can be loaded into the live system
prompt; the full raw history stays on disk and can be looked up on demand
via the recall_person_chat tool.

WhatsApp export line formats handled (Android & iOS, several locales):
    12/06/2025, 14:03 - Anna: Hey, are we still on for Friday?
    [12.06.25, 14:03:21] Anna: Hey, are we still on for Friday?
    6/12/25, 2:03 PM - Anna: Hey, are we still on for Friday?
"""

import json
from core.secrets import get_gemini_key
import re
from pathlib import Path

from memory.memory_manager import upsert_person, get_person_messages


_LINE_RE = re.compile(
    r"""^
        (?:
            \[\d{1,4}[./-]\d{1,2}[./-]\d{1,4},?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?\]\s*
            |
            \d{1,4}[./-]\d{1,2}[./-]\d{1,4},?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?\s*-\s*
        )
        ([^:]{1,60}):\s*
        (.*)$
    """,
    re.VERBOSE,
)


_SYSTEM_HINTS = (
    "messages and calls are end-to-end encrypted",
    "created this group",
    "added you",
    "changed the subject",
    "changed this group's icon",
    "joined using this group's invite link",
    "security code changed",
    "<media omitted>",
)


def _get_api_key() -> str:
    config_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    return get_gemini_key()


def _gemini_client():
    from google import genai
    client = genai.Client(api_key=_get_api_key())

    class _Wrap:
        def generate_content(self, contents):
            return client.models.generate_content(
                model="gemini-2.5-flash", contents=contents
            )

    return _Wrap()


def _parse_chat(text: str) -> dict[str, list[str]]:
    """Group every message verbatim by sender name. Nothing is filtered
    out here except WhatsApp's own system notices — every real message,
    however short or trivial, is kept exactly as written."""
    by_sender: dict[str, list[str]] = {}
    current_sender = None

    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff\u200e ").rstrip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if m:
            sender = m.group(1).strip()
            msg    = m.group(2)
            current_sender = sender
            if msg and not any(h in msg.lower() for h in _SYSTEM_HINTS):
                by_sender.setdefault(sender, []).append(msg)
        elif current_sender:


            if line and not any(h in line.lower() for h in _SYSTEM_HINTS):
                msgs = by_sender.setdefault(current_sender, [])
                if msgs:
                    msgs[-1] = msgs[-1] + "\n" + line
                else:
                    msgs.append(line)

    return by_sender


def _summarize_person(name: str, messages: list[str]) -> dict:
    """Generate a SHORT compact recap for the live prompt only — this does
    not decide what gets stored (everything is stored regardless), it only
    decides what gets surfaced into the system prompt by default."""
    sample = messages[-300:]
    joined = "\n".join(f"- {m}" for m in sample)[:12000]

    prompt = (
        f"Below are real WhatsApp messages sent by a person named '{name}'. "
        f"Write a VERY short recap (max 2 sentences, under 220 characters total) "
        f"capturing who they seem to be and what's notable — relationship to the "
        f"user if it's clear, job, interests, ongoing topics. "
        f"Return ONLY a JSON object, no markdown, no commentary:\n"
        f'{{"relationship": "<short label like friend, sister, colleague, or '
        f'empty string if unclear>", "summary": "<max 220 chars>"}}\n\n'
        f"Messages from {name}:\n{joined}"
    )

    try:
        model    = _gemini_client()
        response = model.generate_content(prompt)
        raw      = response.text.strip()
        raw      = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data     = json.loads(raw)
        summary  = (data.get("summary") or "").strip()[:220]
        rel      = (data.get("relationship") or "").strip()
        return {"relationship": rel, "summary": summary}
    except Exception as e:
        print(f"[WhatsAppImport] Summary generation failed for {name}: {e}")


        return {"relationship": "", "summary": ""}


def import_whatsapp_chat(parameters: dict, player=None, speak=None) -> str:
    file_path_str = (parameters.get("file_path") or "").strip()
    if not file_path_str:
        return "No chat file path provided."

    path = Path(file_path_str)
    if not path.exists() or not path.is_file():
        return f"File not found: {file_path_str}"

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Could not read the file: {e}"

    by_sender = _parse_chat(text)
    if not by_sender:
        return (
            "This doesn't look like a WhatsApp chat export — I couldn't find any "
            "timestamped messages in it."
        )

    me_name = (parameters.get("me_name") or "").strip()
    senders = sorted(by_sender.items(), key=lambda kv: -len(kv[1]))

    imported = []
    total_msgs = 0
    for name, messages in senders:
        if me_name and name.lower() == me_name.lower():
            continue
        if not messages:
            continue


        recap = _summarize_person(name, messages)
        upsert_person(
            name,
            messages,
            relationship=recap["relationship"],
            summary=recap["summary"],
        )
        imported.append((name, len(messages)))
        total_msgs += len(messages)

    log_msg = f"[WhatsAppImport] {path.name}: stored {total_msgs} messages across {len(imported)} people"
    print(log_msg)
    if player:
        try:
            player.write_log(
                f"SYS: Stored {total_msgs} messages from {len(imported)} people in {path.name}."
            )
        except Exception:
            pass

    if not imported:
        return (
            f"I read the chat ({len(by_sender)} participants found) but had nobody "
            f"left to import after excluding your own messages."
        )

    parts = ", ".join(f"{name} ({count} messages)" for name, count in imported)
    return (
        f"Imported everything from the chat — {total_msgs} messages total across "
        f"{len(imported)} people: {parts}. I kept every message, even the small "
        f"stuff, and I'll bring up what's relevant naturally."
    )


def recall_person_chat(parameters: dict, player=None, speak=None) -> str:
    """Look up the full, verbatim message history stored for one person."""
    name = (parameters.get("name") or "").strip()
    if not name:
        return "No person name provided."

    messages = get_person_messages(name)
    if messages is None:
        return f"I don't have any chat history stored for '{name}'."
    if not messages:
        return f"I have '{name}' on file but no messages stored for them."

    query = (parameters.get("query") or "").strip()
    pool  = messages
    if query:
        ql = query.lower()
        matched = [m for m in messages if ql in m.lower()]
        if matched:
            pool = matched

    limit = max(1, min(int(parameters.get("limit", 40) or 40), 200))
    recent = pool[-limit:]
    joined = "\n".join(f"- {m}" for m in recent)
    return (
        f"{name} has {len(messages)} messages on file"
        + (f" ({len(pool)} matching '{query}')" if query else "")
        + f". Showing the {len(recent)} most relevant:\n{joined}"
    )
