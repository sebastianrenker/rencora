import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
        # Dual-Write (Teil 6/11 Architektur-Review): zusaetzlich in die
        # SQLite memories-Tabelle spiegeln. long_term.json bleibt die
        # primaere Quelle - dieser Schreibvorgang darf nie einen
        # save_memory()-Aufruf zum Scheitern bringen.
        try:
            from database.db import upsert_memory
            for category, entries in memory_update.items():
                if not isinstance(entries, dict):
                    continue
                for key, val in entries.items():
                    value = val.get("value") if isinstance(val, dict) else val
                    if value is not None:
                        upsert_memory(category, key, str(value))
        except Exception:
            pass
    return memory

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


# ──────────────────────────────────────────────────────────────────────────
#  PEOPLE MEMORY — facts about people in the user's life, learned from
#  imported WhatsApp chats. Stored separately from long_term.json so the
#  user's own profile and their contacts' profiles don't mix.
# ──────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────
#  PEOPLE MEMORY — every message a chat participant ever sent, learned from
#  imported WhatsApp chats, stored verbatim and in full. Stored separately
#  from long_term.json so the user's own profile and their contacts'
#  profiles don't mix.
#
#  Each person has:
#    - "messages":  the complete, verbatim list of everything they ever
#                    said, across every import — nothing is summarized,
#                    filtered, or dropped here. This list has no cap.
#    - "summary":   a short, compact recap (kept under SUMMARY_MAX_CHARS)
#                   regenerated after each import — THIS is what actually
#                   gets loaded into the live system prompt, since loading
#                   thousands of raw messages into every conversation isn't
#                   practical. The full message list stays on disk and can
#                   be looked up on demand via recall_person_chat.
# ──────────────────────────────────────────────────────────────────────────

PEOPLE_PATH          = BASE_DIR / "memory" / "people.json"
PEOPLE_MAX_PEOPLE     = 200          # very generous — only a sanity ceiling
SUMMARY_MAX_CHARS     = 220          # per person, used in the live prompt
PROMPT_MAX_PEOPLE     = 40           # how many people's summaries to inject at once
PROMPT_MAX_CHARS      = 6000         # overall prompt-injection ceiling


def _empty_people() -> dict:
    return {"people": {}}


def load_people() -> dict:
    if not PEOPLE_PATH.exists():
        return _empty_people()
    with _lock:
        try:
            data = json.loads(PEOPLE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("people"), dict):
                return data
            return _empty_people()
        except Exception as e:
            print(f"[Memory] ⚠️ People load error: {e}")
            return _empty_people()


def _trim_people(data: dict) -> dict:
    """Only caps the *number* of distinct people, never trims a person's
    own message history — that list is meant to be complete and verbatim."""
    people = data.get("people", {})
    while len(people) > PEOPLE_MAX_PEOPLE:
        oldest = min(people.items(), key=lambda kv: kv[1].get("updated", "0000-00-00"))
        del people[oldest[0]]
        print(f"[Memory] 🗑️  Dropped least-recent person (people limit reached): {oldest[0]}")
    return data


def save_people(data: dict) -> None:
    if not isinstance(data, dict):
        return
    data = _trim_people(data)
    PEOPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        PEOPLE_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def upsert_person(
    name: str,
    messages: list[str],
    relationship: str = "",
    summary: str = "",
) -> None:
    """Append a person's verbatim messages (nothing summarized or dropped)
    and refresh their short prompt-facing summary. Safe to call repeatedly
    for the same person across multiple imports — messages accumulate,
    de-duplicated only when truly identical and adjacent-import repeats."""
    if not name or not name.strip():
        return
    name = name.strip()
    data   = load_people()
    people = data["people"]

    existing_key = next((k for k in people if k.lower() == name.lower()), None)
    key = existing_key or name
    entry = people.get(key, {"messages": [], "relationship": "", "summary": "", "updated": ""})

    existing_msgs = entry.setdefault("messages", [])
    seen = set(existing_msgs)
    for msg in messages:
        msg = (msg or "").strip()
        if not msg:
            continue
        # de-dupe only exact repeats (e.g. re-importing the same export);
        # everything else is kept, including short/trivial lines on purpose
        if msg not in seen:
            existing_msgs.append(msg)
            seen.add(msg)

    if relationship and not entry.get("relationship"):
        entry["relationship"] = relationship
    if summary:
        entry["summary"] = summary[:SUMMARY_MAX_CHARS]

    entry["updated"] = datetime.now().strftime("%Y-%m-%d")
    entry["message_count"] = len(existing_msgs)
    people[key] = entry
    save_people(data)


def get_person_messages(name: str) -> list[str] | None:
    """Look up the full, verbatim message history for one person by name
    (case-insensitive). Returns None if the person isn't known."""
    people = load_people().get("people", {})
    key = next((k for k in people if k.lower() == name.strip().lower()), None)
    if key is None:
        return None
    return people[key].get("messages", [])


def format_people_for_prompt(data: dict | None = None) -> str:
    """Render a compact per-person summary for system-prompt injection.
    The full verbatim message history lives only in people.json and is
    fetched on demand via recall_person_chat — it is never dumped into
    the prompt directly, that would be impractically large."""
    data = data or load_people()
    people = data.get("people", {})
    if not people:
        return ""

    # most-recently-updated people first
    ordered = sorted(people.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)

    lines = []
    for name, info in ordered[:PROMPT_MAX_PEOPLE]:
        rel     = info.get("relationship", "")
        summary = info.get("summary", "")
        count   = info.get("message_count", len(info.get("messages", [])))
        if not summary:
            continue
        header = f"  - {name}" + (f" ({rel})" if rel else "")
        lines.append(f"{header}: {summary}  [{count} messages on file]")

    if not lines:
        return ""

    header = (
        "[PEOPLE YOU KNOW — short recap learned from imported WhatsApp chats. "
        "Reference naturally in conversation, never recite as a list. "
        "Full verbatim chat history per person is available via recall_person_chat "
        "if you need a specific detail that isn't in this recap]\n"
    )
    result = header + "\n".join(lines)
    if len(result) > PROMPT_MAX_CHARS:
        result = result[:PROMPT_MAX_CHARS - 1] + "…"
    return result + "\n"