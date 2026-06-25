"""
SQLite database layer for OPD Audio Generator.
Tables: consultations, utterances, batch_jobs
"""
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent.parent / "data" / "opd_audio.db"


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they do not exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS consultations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            script_path TEXT,
            raw_script TEXT,
            status TEXT DEFAULT 'queued',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            seed INTEGER,
            language TEXT DEFAULT 'hi',
            engine TEXT DEFAULT 'parler',
            noise_settings TEXT DEFAULT '{}',
            speaker_settings TEXT DEFAULT '{}',
            output_dir TEXT,
            error_message TEXT,
            total_utterances INTEGER DEFAULT 0,
            completed_utterances INTEGER DEFAULT 0,
            batch_id TEXT
        );

        CREATE TABLE IF NOT EXISTS utterances (
            id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL REFERENCES consultations(id) ON DELETE CASCADE,
            speaker TEXT NOT NULL,
            text TEXT NOT NULL,
            line_number INTEGER DEFAULT 0,
            status TEXT DEFAULT 'queued',
            audio_path TEXT,
            duration_seconds REAL,
            engine TEXT DEFAULT 'parler',
            voice_description TEXT,
            ref_audio_path TEXT,
            ref_text TEXT,
            language TEXT DEFAULT 'hi',
            error_message TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS batch_jobs (
            id TEXT PRIMARY KEY,
            name TEXT,
            consultation_ids TEXT NOT NULL,
            status TEXT DEFAULT 'queued',
            current_index INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_utterances_consultation ON utterances(consultation_id);
        CREATE INDEX IF NOT EXISTS idx_utterances_status ON utterances(status);
        CREATE INDEX IF NOT EXISTS idx_consultations_status ON consultations(status);
        """)


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return None
    return dict(row)


# ─── Consultations ────────────────────────────────────────────────────────────

def create_consultation(
    name: str,
    raw_script: str,
    script_path: Optional[str] = None,
    language: str = "hi",
    engine: str = "parler",
    seed: Optional[int] = None,
    noise_settings: Optional[Dict] = None,
    speaker_settings: Optional[Dict] = None,
    output_dir: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> str:
    cid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO consultations
               (id, name, script_path, raw_script, status, created_at, updated_at,
                seed, language, engine, noise_settings, speaker_settings, output_dir, batch_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid, name, script_path, raw_script, "queued", now, now,
                seed, language, engine,
                json.dumps(noise_settings or {}),
                json.dumps(speaker_settings or {}),
                output_dir, batch_id,
            ),
        )
    return cid


def get_consultation(cid: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM consultations WHERE id=?", (cid,)).fetchone()
    d = _row_to_dict(row)
    if d:
        d["noise_settings"] = json.loads(d.get("noise_settings") or "{}")
        d["speaker_settings"] = json.loads(d.get("speaker_settings") or "{}")
    return d


def list_consultations(batch_id: Optional[str] = None) -> List[Dict]:
    with get_conn() as conn:
        if batch_id:
            rows = conn.execute(
                "SELECT * FROM consultations WHERE batch_id=? ORDER BY created_at DESC", (batch_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM consultations ORDER BY created_at DESC"
            ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        d["noise_settings"] = json.loads(d.get("noise_settings") or "{}")
        d["speaker_settings"] = json.loads(d.get("speaker_settings") or "{}")
        result.append(d)
    return result


def update_consultation(cid: str, **kwargs):
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    for key in ["noise_settings", "speaker_settings"]:
        if key in kwargs and isinstance(kwargs[key], dict):
            kwargs[key] = json.dumps(kwargs[key])
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [cid]
    with get_conn() as conn:
        conn.execute(f"UPDATE consultations SET {cols} WHERE id=?", vals)


def delete_consultation(cid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM consultations WHERE id=?", (cid,))


# ─── Utterances ───────────────────────────────────────────────────────────────

def create_utterance(
    consultation_id: str,
    speaker: str,
    text: str,
    line_number: int = 0,
    sort_order: int = 0,
    engine: str = "parler",
    voice_description: str = "",
    ref_audio_path: Optional[str] = None,
    ref_text: Optional[str] = None,
    language: str = "hi",
) -> str:
    uid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO utterances
               (id, consultation_id, speaker, text, line_number, sort_order, status,
                engine, voice_description, ref_audio_path, ref_text, language, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, consultation_id, speaker, text, line_number, sort_order,
             "queued", engine, voice_description, ref_audio_path, ref_text, language, now),
        )
    return uid


def get_utterances(consultation_id: str) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM utterances WHERE consultation_id=? ORDER BY sort_order ASC",
            (consultation_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_utterance(uid: str, **kwargs):
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [uid]
    with get_conn() as conn:
        conn.execute(f"UPDATE utterances SET {cols} WHERE id=?", vals)


def get_queued_utterances_for_consultation(cid: str) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM utterances WHERE consultation_id=? AND status='queued' ORDER BY sort_order ASC",
            (cid,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_utterances_by_status(cid: str) -> Dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM utterances WHERE consultation_id=? GROUP BY status",
            (cid,),
        ).fetchall()
    return {row["status"]: row["cnt"] for row in rows}


def reset_stuck_utterances():
    """On startup: reset processing→queued so they will be re-attempted."""
    with get_conn() as conn:
        conn.execute("UPDATE utterances SET status='queued' WHERE status='processing'")
        conn.execute(
            "UPDATE consultations SET status='queued' WHERE status='processing'"
        )


# ─── Batch Jobs ───────────────────────────────────────────────────────────────

def create_batch_job(name: str, consultation_ids: List[str]) -> str:
    bid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO batch_jobs (id, name, consultation_ids, status, current_index, total, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (bid, name, json.dumps(consultation_ids), "queued", 0, len(consultation_ids), now, now),
        )
    return bid


def get_batch_job(bid: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM batch_jobs WHERE id=?", (bid,)).fetchone()
    d = _row_to_dict(row)
    if d:
        d["consultation_ids"] = json.loads(d.get("consultation_ids") or "[]")
    return d


def list_batch_jobs() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM batch_jobs ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        d["consultation_ids"] = json.loads(d.get("consultation_ids") or "[]")
        result.append(d)
    return result


def update_batch_job(bid: str, **kwargs):
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [bid]
    with get_conn() as conn:
        conn.execute(f"UPDATE batch_jobs SET {cols} WHERE id=?", vals)
