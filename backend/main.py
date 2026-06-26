"""
FastAPI main application — OPD Audio Generator backend.
Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import json
import logging
import os
import random
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).parent))

from auth import APP_PASSWORD, BasicAuthMiddleware
from database import (
    create_batch_job,
    create_consultation,
    create_utterance,
    delete_consultation,
    get_batch_job,
    get_consultation,
    get_utterances,
    init_db,
    list_batch_jobs,
    list_consultations,
    update_batch_job,
    update_consultation,
)
from job_runner import get_runner, start_runner, stop_runner
from noise_mixer import generate_noise_clips
from script_parser import detect_language_hint, extract_speakers, parse_script
from tts_engine import (
    SPEAKER_VOICE_PROFILES,
    check_engine_availability,
    get_voice_profile,
    get_random_voice_profile,
)
from zip_builder import build_all_zip, build_consultation_zip

# ─── Logging Setup (Rotating File + Console) ────────────────────────────────

def setup_logging():
    log_dir = Path("/logs") if os.path.exists("/logs") else Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "opd_audio.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Rotating file handler (100 MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=100_000_000, backupCount=5
    )
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler (for docker logs)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    root_logger.addHandler(console_handler)

    logging.info(f"Logging to {log_file} (rotating)")

setup_logging()
logger = logging.getLogger(__name__)

# ─── Signal Handlers for Graceful Shutdown ──────────────────────────────────

def shutdown_gracefully(signum, frame):
    logger.info(f"Received signal {signum}, stopping job runner...")
    runner = get_runner()
    if runner:
        stop_runner(runner)
    logger.info("Shutdown complete. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_gracefully)
signal.signal(signal.SIGINT, shutdown_gracefully)

# ─── Paths ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"
UPLOADS_DIR = DATA_DIR / "uploads"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

for d in [DATA_DIR, OUTPUTS_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OPD Audio Generator",
    description="Convert Indian OPD consultation scripts to realistic audio",
    version="1.0.0",
)

# CORS (allow all for local use)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Password protection (optional)
if APP_PASSWORD:
    app.add_middleware(BasicAuthMiddleware, password=APP_PASSWORD)

# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    generate_noise_clips()
    start_runner()
    logger.info("OPD Audio Generator started")

# ─── Pydantic models ──────────────────────────────────────────────────────────

class SpeakerSettings(BaseModel):
    gender: str = "male"
    age: str = "adult"
    voice_description: Optional[str] = None
    ref_audio_path: Optional[str] = None
    ref_text: Optional[str] = None
    engine: Optional[str] = None
    language: Optional[str] = None

class NoiseSettings(BaseModel):
    enabled: bool = False
    types: Dict[str, bool] = {}
    intensity: float = 0.3

class GenerateRequest(BaseModel):
    name: str
    script: Optional[str] = None
    language: str = "hi"
    engine: str = "parler"
    seed: Optional[int] = None
    speaker_settings: Dict[str, Dict[str, Any]] = {}
    noise_settings: Dict[str, Any] = {}
    randomize: bool = False

class BatchRequest(BaseModel):
    name: str
    scripts: List[Dict[str, Any]]
    engine: str = "parler"
    seed: Optional[int] = None
    speaker_settings: Dict[str, Dict[str, Any]] = {}
    noise_settings: Dict[str, Any] = {}
    randomize: bool = False

# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    engines = check_engine_availability()
    runner = get_runner()
    return {
        "status": "ok",
        "engines": engines,
        "runner_alive": runner.is_alive() if runner else False,
        "current_job": runner.current_job if runner else None,
    }

# ─── Script parsing ──────────────────────────────────────────────────────────

@app.post("/api/parse")
async def parse_script_endpoint(
    file: Optional[UploadFile] = File(None),
    script: Optional[str] = Form(None),
):
    if file:
        content = await file.read()
        filename = file.filename or "script.txt"
        turns = parse_script(content, filename)
    elif script:
        turns = parse_script(script, "script.txt")
    else:
        raise HTTPException(400, "Provide file or script text")

    speakers = extract_speakers(turns)
    lang = detect_language_hint(" ".join(t["text"] for t in turns))
    return {
        "turns": turns,
        "speakers": speakers,
        "detected_language": lang,
        "total_turns": len(turns),
    }

# ─── Consultations ────────────────────────────────────────────────────────────

@app.post("/api/consultations")
async def create(
    file: Optional[UploadFile] = File(None),
    request_json: Optional[str] = Form(None),
):
    if request_json:
        req = GenerateRequest(**json.loads(request_json))
    else:
        raise HTTPException(400, "Provide request_json form field")

    if file:
        content = await file.read()
        filename = file.filename or "script.txt"
        script_path = UPLOADS_DIR / filename
        script_path.write_bytes(content)
        turns = parse_script(content, filename)
        raw_script = content.decode("utf-8", errors="replace")
    elif req.script:
        raw_script = req.script
        turns = parse_script(raw_script, "script.txt")
        script_path = None
    else:
        raise HTTPException(400, "Provide file or script text")

    if not turns:
        raise HTTPException(400, "Could not detect any speaker turns in the script")

    seed = req.seed if req.seed is not None else random.randint(1, 999999)
    speakers = extract_speakers(turns)

    noise_settings = req.noise_settings
    if getattr(req, "randomize", False):
        noise_keys = ["hospital_ambience", "fan", "ac", "keyboard", "phone", "cough", "door", "chatter", "opd_mix"]
        num_noises = random.randint(1, 3)
        selected_noises = random.sample(noise_keys, num_noises)
        types = {k: (k in selected_noises) for k in noise_keys}
        intensity = round(random.uniform(0.15, 0.40), 2)
        noise_settings = {"enabled": True, "types": types, "intensity": intensity}

    speaker_settings = {}
    for sp in speakers:
        user_sp = req.speaker_settings.get(sp, {})
        if getattr(req, "randomize", False):
            gender = random.choice(["male", "female"])
            sp_lower = sp.lower()
            if "doc" in sp_lower or "dr" in sp_lower:
                age = "adult"
            elif "patient" in sp_lower or "pt" in sp_lower:
                age = random.choices(["adult", "elderly", "young"], weights=[0.7, 0.2, 0.1])[0]
            else:
                age = random.choice(["adult", "young"])
            engine = req.engine
            lang = req.language
            vdesc = get_random_voice_profile(sp, gender, age, lang)
        else:
            gender = user_sp.get("gender", "male")
            age = user_sp.get("age", "adult")
            engine = user_sp.get("engine") or req.engine
            lang = user_sp.get("language") or req.language
            vdesc = user_sp.get("voice_description") or get_voice_profile(sp, gender, age, lang)

        speaker_settings[sp] = {
            "gender": gender,
            "age": age,
            "engine": engine,
            "language": lang,
            "voice_description": vdesc,
        }

    cid = create_consultation(
        name=req.name,
        raw_script=raw_script,
        script_path=str(script_path) if script_path else None,
        language=req.language,
        engine=req.engine,
        seed=seed,
        noise_settings=noise_settings,
        speaker_settings=speaker_settings,
        output_dir=str(OUTPUTS_DIR / "PLACEHOLDER"),
    )
    output_dir = OUTPUTS_DIR / cid
    output_dir.mkdir(parents=True, exist_ok=True)
    update_consultation(cid, output_dir=str(output_dir), total_utterances=len(turns))

    for i, turn in enumerate(turns):
        sp = turn["speaker"]
        sp_cfg = speaker_settings.get(sp, {})
        create_utterance(
            consultation_id=cid,
            speaker=sp,
            text=turn["text"],
            line_number=turn.get("line_number", i),
            sort_order=i,
            engine=sp_cfg.get("engine", req.engine),
            voice_description=sp_cfg.get("voice_description", ""),
            language=sp_cfg.get("language", req.language),
        )

    logger.info(f"Created consultation {cid[:8]}: {len(turns)} utterances")
    return {"id": cid, "name": req.name, "total_utterances": len(turns), "seed": seed}

@app.get("/api/consultations")
async def list_all():
    return list_consultations()

@app.get("/api/consultations/{cid}")
async def get_one(cid: str):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "Not found")
    utterances = get_utterances(cid)
    return {**c, "utterances": utterances}

@app.delete("/api/consultations/{cid}")
async def delete_one(cid: str):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "Not found")
    output_dir = Path(c.get("output_dir") or OUTPUTS_DIR / cid)
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
    delete_consultation(cid)
    return {"deleted": cid}

@app.get("/api/consultations/{cid}/progress")
async def get_progress(cid: str):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "Not found")
    runner = get_runner()
    progress = runner.get_progress(cid) if runner else {}
    return {**progress, "status": c["status"]}

@app.get("/api/consultations/{cid}/utterances/{uid}/audio")
async def stream_utterance_audio(cid: str, uid: str, download: bool = False):
    utterances = get_utterances(cid)
    utt = next((u for u in utterances if u["id"] == uid), None)
    if not utt:
        raise HTTPException(404, "Utterance not found")
    ap = utt.get("audio_path")
    if not ap or not Path(ap).exists():
        raise HTTPException(404, "Audio not generated yet")
    media_type = "audio/mpeg" if Path(ap).suffix == ".mp3" else "audio/wav"
    if download:
        filename = Path(ap).name
        return FileResponse(ap, media_type=media_type, filename=filename)
    return FileResponse(ap, media_type=media_type)

@app.get("/api/consultations/{cid}/audio/full")
async def stream_full_audio(cid: str, download: bool = False):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "Not found")
    full_path = Path(c.get("output_dir", OUTPUTS_DIR / cid)) / "full_consultation.mp3"
    if not full_path.exists():
        full_path = full_path.with_suffix(".wav")
    if not full_path.exists():
        raise HTTPException(404, "Full audio not ready yet")
    media_type = "audio/mpeg" if full_path.suffix == ".mp3" else "audio/wav"
    if download:
        name = c.get("name", "consultation").replace(" ", "_")
        return FileResponse(
            str(full_path),
            media_type=media_type,
            filename=f"{name}{full_path.suffix}"
        )
    return FileResponse(str(full_path), media_type=media_type)

@app.get("/api/consultations/{cid}/download")
async def download_zip(cid: str):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "Not found")
    utterances = get_utterances(cid)
    output_dir = Path(c.get("output_dir") or OUTPUTS_DIR / cid)
    zip_bytes = build_consultation_zip(c, utterances, output_dir)
    name = c.get("name", "consultation").replace(" ", "_")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )

@app.get("/api/download-all")
async def download_all_zip():
    consultations = list_consultations()
    data = []
    for c in consultations:
        if c["status"] == "done":
            utterances = get_utterances(c["id"])
            output_dir = Path(c.get("output_dir") or OUTPUTS_DIR / c["id"])
            data.append({"consultation": c, "utterances": utterances, "output_dir": str(output_dir)})
    if not data:
        raise HTTPException(404, "No completed consultations to download")
    zip_bytes = build_all_zip(data)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="all_consultations.zip"'},
    )

# ─── Batch ────────────────────────────────────────────────────────────────────

@app.post("/api/batch")
async def create_batch(req: BatchRequest):
    consultation_ids = []
    seed_base = req.seed if req.seed is not None else random.randint(1, 999999)

    for i, script_item in enumerate(req.scripts):
        name = script_item.get("name", f"Script {i+1}")
        raw_script = script_item.get("script", "")
        language = script_item.get("language", req.language)
        turns = parse_script(raw_script, "script.txt")
        if not turns:
            continue

        speakers = extract_speakers(turns)
        noise_settings = req.noise_settings
        if getattr(req, "randomize", False):
            noise_keys = ["hospital_ambience", "fan", "ac", "keyboard", "phone", "cough", "door", "chatter", "opd_mix"]
            num_noises = random.randint(1, 3)
            selected_noises = random.sample(noise_keys, num_noises)
            types = {k: (k in selected_noises) for k in noise_keys}
            intensity = round(random.uniform(0.15, 0.40), 2)
            noise_settings = {"enabled": True, "types": types, "intensity": intensity}

        speaker_settings = {}
        for sp in speakers:
            user_sp = req.speaker_settings.get(sp, {})
            if getattr(req, "randomize", False):
                gender = random.choice(["male", "female"])
                sp_lower = sp.lower()
                if "doc" in sp_lower or "dr" in sp_lower:
                    age = "adult"
                elif "patient" in sp_lower or "pt" in sp_lower:
                    age = random.choices(["adult", "elderly", "young"], weights=[0.7, 0.2, 0.1])[0]
                else:
                    age = random.choice(["adult", "young"])
                engine = req.engine
                lang = language
                vdesc = get_random_voice_profile(sp, gender, age, lang)
            else:
                gender = user_sp.get("gender", "male")
                age = user_sp.get("age", "adult")
                engine = user_sp.get("engine") or req.engine
                lang = user_sp.get("language") or language
                vdesc = user_sp.get("voice_description") or get_voice_profile(sp, gender, age, lang)
            speaker_settings[sp] = {"gender": gender, "age": age, "engine": engine, "language": lang, "voice_description": vdesc}

        cid = create_consultation(
            name=name, raw_script=raw_script, language=language, engine=req.engine,
            seed=seed_base + i, noise_settings=noise_settings,
            speaker_settings=speaker_settings,
        )
        output_dir = OUTPUTS_DIR / cid
        output_dir.mkdir(parents=True, exist_ok=True)
        update_consultation(cid, output_dir=str(output_dir), total_utterances=len(turns))

        for j, turn in enumerate(turns):
            sp = turn["speaker"]
            sp_cfg = speaker_settings.get(sp, {})
            create_utterance(
                consultation_id=cid, speaker=sp, text=turn["text"],
                line_number=turn.get("line_number", j), sort_order=j,
                engine=sp_cfg.get("engine", req.engine),
                voice_description=sp_cfg.get("voice_description", ""),
                language=sp_cfg.get("language", language),
            )

        consultation_ids.append(cid)
        update_consultation(cid, batch_id="PENDING")

    bid = create_batch_job(req.name, consultation_ids)
    for cid in consultation_ids:
        update_consultation(cid, batch_id=bid)

    logger.info(f"Created batch {bid[:8]}: {len(consultation_ids)} consultations")
    return {"batch_id": bid, "consultation_ids": consultation_ids, "total": len(consultation_ids)}

@app.get("/api/batch")
async def list_batches():
    return list_batch_jobs()

@app.get("/api/batch/{bid}")
async def get_batch(bid: str):
    b = get_batch_job(bid)
    if not b:
        raise HTTPException(404, "Not found")
    consultations = list_consultations(batch_id=bid)
    return {**b, "consultations": consultations}

@app.get("/api/batch/{bid}/download")
async def download_batch_zip(bid: str):
    b = get_batch_job(bid)
    if not b:
        raise HTTPException(404, "Not found")
    consultations = list_consultations(batch_id=bid)
    data = []
    for c in consultations:
        utterances = get_utterances(c["id"])
        output_dir = Path(c.get("output_dir") or OUTPUTS_DIR / c["id"])
        data.append({"consultation": c, "utterances": utterances, "output_dir": str(output_dir)})
    zip_bytes = build_all_zip(data)
    name = b.get("name", "batch").replace(" ", "_")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )

# ─── Voice profiles ───────────────────────────────────────────────────────────

@app.get("/api/voice-profiles")
async def get_voice_profiles():
    return SPEAKER_VOICE_PROFILES

@app.get("/api/noise-types")
async def get_noise_types():
    return {
        "hospital_ambience": "Hospital Ambience",
        "fan": "Fan Hum",
        "ac": "AC Hum",
        "keyboard": "Keyboard Typing",
        "phone": "Phone Ring",
        "cough": "Coughing",
        "door": "Door Sounds",
        "chatter": "Nearby Chatter",
        "opd_mix": "Real Indian OPD Mix",
    }

# ─── Serve React frontend ─────────────────────────────────────────────────────

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {"message": "OPD Audio Generator API. Frontend not built yet. Run: cd frontend && npm run build"}

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)