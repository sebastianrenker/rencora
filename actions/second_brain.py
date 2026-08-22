"""
second_brain.py — RENCORA Second Brain

Persoenliche Wissensablage: Ein Handy oder der Desktop-Client wirft eine
Datei auf das " Second Brain"-Feld im Remote Dashboard, RENCORA wertet
sie aus (Text/Bild/PDF/Audio/... — je nach Typ) und speichert eine
durchsuchbare Zusammenfassung + die wichtigsten Fakten dauerhaft in
memory/second_brain.json. Spaeter kann man RENCORA einfach fragen
("Was stand nochmal in dem Rezept, das ich letzte Woche reingeworfen
habe?") und es per second_brain_recall wiederfinden.

Bewusst getrennt von save_memory (kurze Fakten wie Name/Vorlieben) und
von import_whatsapp_chat (Chat-Verlaeufe) — das hier ist fuer
Dokumente/Notizen/Belege/Screenshots etc.
"""

import json
from core.secrets import get_gemini_key
import re
import sys
import time
import uuid
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR   = _get_base_dir()
STORE_PATH = BASE_DIR / "memory" / "second_brain.json"

MAX_STORED_TEXT_CHARS = 20000
MAX_ENTRIES            = 2000


def _get_api_key() -> str:
    return get_gemini_key()


def _gemini_client():
    from google import genai
    return genai.Client(api_key=_get_api_key())


def _load() -> list:
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    STORE_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _detect_type(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "heif"}:
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext == "docx":
        return "docx"
    if ext in {"txt", "md", "rtf"}:
        return "text"
    if ext in {"csv", "tsv"}:
        return "csv"
    if ext == "json":
        return "json"
    if ext in {"py", "js", "ts", "html", "css", "java", "c", "cpp", "go", "rs", "sh"}:
        return "code"
    if ext in {"mp3", "wav", "m4a", "aac", "flac", "ogg", "opus"}:
        return "audio"
    if ext in {"mp4", "mov", "avi", "mkv", "webm"}:
        return "video"
    if ext in {"pptx", "ppt"}:
        return "pptx"
    return "other"


def _extract_pdf_text(path: Path, max_chars: int = 60000) -> str:
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except ImportError:
        try:
            import PyPDF2
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
        except ImportError:
            return ""
    except Exception:
        return ""
    return text[:max_chars]


def _extract_docx_text(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def _extract_image_text(path: Path) -> str:
    try:
        from PIL import Image
        client = _gemini_client()
        img = Image.open(path)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "Describe this image in detail, and transcribe any visible "
                "text verbatim (receipts, screenshots, handwriting, signs, etc.).",
                img,
            ],
        )
        return response.text.strip()
    except Exception as e:
        return f"[Bildanalyse fehlgeschlagen: {e}]"


def _extract_via_file_processor(path: Path, action: str) -> str:
    """Fallback fuer Audio/Video/pptx/Sonstiges: nutzt file_processor.py."""
    try:
        from actions.file_processor import file_processor
        return file_processor({"file_path": str(path), "action": action}, player=None)
    except Exception as e:
        return f"[Verarbeitung fehlgeschlagen: {e}]"


def _extract_content(path: Path, file_type: str) -> str:
    if file_type == "pdf":
        text = _extract_pdf_text(path)
        return text if text.strip() else "[Kein Text extrahierbar — evtl. gescanntes PDF]"
    if file_type == "docx":
        text = _extract_docx_text(path)
        return text if text.strip() else "[Kein Text extrahierbar]"
    if file_type in ("text", "csv", "json", "code"):
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:60000]
        except Exception as e:
            return f"[Lesen fehlgeschlagen: {e}]"
    if file_type == "image":
        return _extract_image_text(path)
    if file_type == "audio":
        return _extract_via_file_processor(path, "transcribe")
    if file_type == "video":
        return _extract_via_file_processor(path, "transcribe")
    if file_type == "pptx":
        return _extract_via_file_processor(path, "extract_text")
    return _extract_via_file_processor(path, "summarize")


def _summarize_and_tag(filename: str, content: str, note: str = "") -> dict:
    prompt = (
        "You are filing a document into a personal knowledge base (a "
        "'second brain'). Given the extracted content below, respond with "
        "STRICT JSON only, no markdown fences, no preamble, matching this "
        "shape exactly:\n"
        '{"summary": "2-4 sentence summary in German", '
        '"key_facts": ["short fact 1", "short fact 2", "..."], '
        '"tags": ["lowercase-tag1", "lowercase-tag2"]}\n\n'
        f"Filename: {filename}\n"
        f"User note (if any): {note or '(none)'}\n\n"
        f"Content:\n{content[:30000]}"
    )
    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        return {
            "summary":   str(data.get("summary", ""))[:1000],
            "key_facts": [str(x)[:200] for x in (data.get("key_facts") or [])][:10],
            "tags":      [str(x)[:40]  for x in (data.get("tags") or [])][:10],
        }
    except Exception as e:
        print(f"[SecondBrain]  Summarize/tag failed: {e}")
        return {"summary": content[:300].strip() or "(keine Zusammenfassung moeglich)",
                "key_facts": [], "tags": []}


def second_brain_save(parameters: dict, player=None, speak=None) -> str:
    """Verarbeitet eine hochgeladene Datei und speichert sie dauerhaft im
    Second Brain (Zusammenfassung + Kernfakten + Volltext, durchsuchbar)."""
    params    = parameters or {}
    file_path = params.get("file_path", "").strip()
    note      = params.get("note", "").strip()

    if not file_path:
        return "No file path provided for Second Brain."
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return f"File not found: {file_path}"

    file_type = _detect_type(path)
    print(f"[SecondBrain]  Processing {path.name} ({file_type})...")
    if player:
        player.write_log(f"[SecondBrain] Verarbeite {path.name} ({file_type})...")

    content = _extract_content(path, file_type)
    meta    = _summarize_and_tag(path.name, content, note)

    entry = {
        "id":          uuid.uuid4().hex[:12],
        "filename":    path.name,
        "file_type":   file_type,
        "saved_at":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "note":        note,
        "summary":     meta["summary"],
        "key_facts":   meta["key_facts"],
        "tags":        meta["tags"],
        "text":        content[:MAX_STORED_TEXT_CHARS],
        "source_path": str(path),
    }

    entries = _load()
    entries.append(entry)
    _save(entries)


    try:
        from database.db import insert_knowledge
        insert_knowledge(
            source_type="second_brain", source_ref=entry["id"],
            summary=meta["summary"], tags=meta["tags"],
        )
    except Exception:
        pass

    print(f"[SecondBrain]  Saved: {path.name} — {meta['summary'][:80]}")
    facts_str = "; ".join(meta["key_facts"][:3])
    return (
        f"Second Brain gespeichert: '{path.name}'. "
        f"Zusammenfassung: {meta['summary']}"
        + (f" Wichtigste Punkte: {facts_str}." if facts_str else "")
    )


def second_brain_recall(parameters: dict, player=None, speak=None) -> str:
    """Durchsucht das Second Brain nach einem Stichwort/Thema und gibt die
    passendsten Eintraege (Zusammenfassung + Kernfakten) zurueck."""
    params = parameters or {}
    query  = params.get("query", "").strip().lower()
    if not query:
        return "Please provide a search term for the Second Brain."

    entries = _load()
    if not entries:
        return "Das Second Brain ist noch leer — es wurde noch nichts gespeichert."

    scored = []
    for e in entries:
        haystack = " ".join([
            e.get("filename", ""), e.get("summary", ""), e.get("note", ""),
            " ".join(e.get("tags", [])), " ".join(e.get("key_facts", [])),
            e.get("text", "")[:5000],
        ]).lower()
        if query in haystack:
            score = haystack.count(query)
            scored.append((score, e))

    if not scored:
        return f"Nichts im Second Brain gefunden zu: {query}"

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [e for _, e in scored[:5]]

    lines = [f"Second Brain — {len(top)} Treffer zu '{query}':"]
    for e in top:
        lines.append(f"\n {e['filename']} ({e['saved_at']})")
        lines.append(f"   {e['summary']}")
        if e.get("key_facts"):
            lines.append("   • " + "\n   • ".join(e["key_facts"][:3]))
    return "\n".join(lines)
