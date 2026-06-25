"""
Script parser: extract speaker turns from TXT, Markdown, PDF, DOCX, JSON.
Returns a list of {speaker, text, line_number} dicts.
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Optional


# Known speaker roles (case-insensitive prefix match)
KNOWN_SPEAKERS = [
    "doctor", "dr", "physician",
    "patient", "pt",
    "nurse",
    "attendant",
    "receptionist",
    "relative", "family",
    "lab", "lab staff", "technician",
    "narrator",
]

# Patterns for speaker detection:
SPEAKER_PATTERNS = [
    # "Doctor: ..."  or  "ડોક્ટર: ..." or "DR. SHARMA: ..."
    re.compile(r"^([^\d\W_][^\d_\[\]\(\)\*:]{0,30}?)\s*:\s*(.+)$"),
    # "[Doctor] ..."
    re.compile(r"^\[([^\d\W_][^\d_\[\]\(\)\*:]{0,30}?)\]\s*(.*)$"),
    # "(Doctor) ..."
    re.compile(r"^\(([^\d\W_][^\d_\[\]\(\)\*:]{0,30}?)\)\s*(.*)$"),
    # "**Doctor**: ..."  or  "*Doctor*: ..."
    re.compile(r"^\*{1,2}([^\d\W_][^\d_\[\]\(\)\*:]{0,30}?)\*{1,2}\s*:\s*(.+)$"),
]

SKIP_HEADERS = ["language", "duration", "title", "topic", "date", "time", "setting", "scene"]


def _normalize_speaker(raw: str) -> str:
    """Normalize speaker name to Title Case, collapse whitespace."""
    name = raw.strip().title()
    name = re.sub(r"\s+", " ", name)
    mappings = {
        "Dr": "Doctor",
        "Pt": "Patient",
        "Lab Staff": "Lab Staff",
        "Lab": "Lab Staff",
        "ડોક્ટર": "Doctor",
        "દર્દી": "Patient",
        "डॉक्टर": "Doctor",
        "मरीज़": "Patient",
        "मरीज": "Patient",
    }
    return mappings.get(name, name)


def _parse_lines(lines: List[str]) -> List[Dict]:
    """Parse a list of text lines into speaker turns."""
    turns = []
    current_speaker = None
    current_text_parts = []
    line_num = 0

    def flush():
        if current_speaker and current_text_parts:
            text = " ".join(current_text_parts).strip()
            if text:
                turns.append({
                    "speaker": current_speaker,
                    "text": text,
                    "line_number": line_num,
                })

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        matched = False
        for pattern in SPEAKER_PATTERNS:
            m = pattern.match(stripped)
            if m:
                raw_speaker = m.group(1).strip()
                if raw_speaker.lower() in SKIP_HEADERS:
                    matched = True
                    break  # Skip this line entirely

                flush()
                current_speaker = _normalize_speaker(raw_speaker)
                current_text_parts = [m.group(2).strip()] if m.group(2).strip() else []
                line_num = i + 1
                matched = True
                break

        if not matched and current_speaker:
            # Continuation of previous speaker's text
            current_text_parts.append(stripped)

    flush()
    return turns


def parse_txt(content: str) -> List[Dict]:
    return _parse_lines(content.splitlines())


def parse_pdf(path: Path) -> List[Dict]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        text = "\n".join(page.get_text() for page in doc)
        return parse_txt(text)
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: pip install pymupdf")


def parse_docx(path: Path) -> List[Dict]:
    try:
        from docx import Document
        doc = Document(str(path))
        lines = [para.text for para in doc.paragraphs]
        return _parse_lines(lines)
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")


def parse_json(content: str) -> List[Dict]:
    """
    Accepts JSON in multiple formats:
    - List of {speaker, text} dicts
    - List of [speaker, text] pairs
    - {"turns": [...]}
    """
    data = json.loads(content)
    if isinstance(data, dict) and "turns" in data:
        data = data["turns"]
    turns = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            speaker = _normalize_speaker(str(item.get("speaker", item.get("role", "Unknown"))))
            text = str(item.get("text", item.get("content", "")))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            speaker = _normalize_speaker(str(item[0]))
            text = str(item[1])
        else:
            continue
        if text.strip():
            turns.append({"speaker": speaker, "text": text.strip(), "line_number": i + 1})
    return turns


def parse_script(content_or_path, filename: str = "") -> List[Dict]:
    """
    Main entry point. Accepts either file content (str/bytes) or a Path.
    Detects format from filename extension.
    """
    ext = Path(filename).suffix.lower() if filename else ""

    is_file_path = False
    if isinstance(content_or_path, Path):
        try:
            is_file_path = content_or_path.exists()
        except OSError:
            pass
    elif isinstance(content_or_path, str) and len(content_or_path) < 2048:
        try:
            is_file_path = Path(content_or_path).exists()
        except OSError:
            pass

    if is_file_path:
        path = Path(content_or_path)
        ext = ext or path.suffix.lower()
        if ext == ".pdf":
            return parse_pdf(path)
        elif ext in (".docx", ".doc"):
            return parse_docx(path)
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            if ext == ".json":
                return parse_json(content)
            return parse_txt(content)
    else:
        content = content_or_path
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        if ext == ".json":
            return parse_json(content)
        return parse_txt(content)


def extract_speakers(turns: List[Dict]) -> List[str]:
    """Return unique speakers in order of first appearance."""
    seen = []
    for t in turns:
        if t["speaker"] not in seen:
            seen.append(t["speaker"])
    return seen


def detect_language_hint(text: str) -> str:
    """
    Simple heuristic to detect the primary language from script text.
    Returns BCP-47-ish language code.
    """
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))
    tamil = len(re.findall(r'[\u0B80-\u0BFF]', text))
    telugu = len(re.findall(r'[\u0C00-\u0C7F]', text))
    kannada = len(re.findall(r'[\u0C80-\u0CFF]', text))
    malayalam = len(re.findall(r'[\u0D00-\u0D7F]', text))
    bengali = len(re.findall(r'[\u0980-\u09FF]', text))
    gujarati = len(re.findall(r'[\u0A80-\u0AFF]', text))
    gurmukhi = len(re.findall(r'[\u0A00-\u0A7F]', text))

    scores = {
        "hi": devanagari,
        "ta": tamil,
        "te": telugu,
        "kn": kannada,
        "ml": malayalam,
        "bn": bengali,
        "gu": gujarati,
        "pa": gurmukhi,
    }
    best = max(scores, key=scores.get)
    if scores[best] > 10:
        return best
    return "hi"  # default to Hindi for Hinglish/English
