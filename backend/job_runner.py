"""
Background job runner.
A single daemon thread polls the SQLite DB for queued consultations/utterances
and processes them one at a time. Survives FastAPI restarts — just picks up
where it left off.
"""
import logging
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from database import (
    get_consultation, get_utterances, get_queued_utterances_for_consultation,
    list_consultations, update_consultation, update_utterance,
    count_utterances_by_status, reset_stuck_utterances,
    get_batch_job, list_batch_jobs, update_batch_job,
)
from noise_mixer import mix_noise
from tts_engine import generate_speech
from zip_builder import save_consultation_files

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"


class JobRunner(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="JobRunner")
        self._stop_event = threading.Event()
        self.current_job: Optional[str] = None  # consultation_id being processed

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info("JobRunner started")
        # On startup, reset any stuck jobs
        reset_stuck_utterances()
        self._resume_incomplete_consultations()

        while not self._stop_event.is_set():
            try:
                self._process_next()
            except Exception as e:
                logger.exception(f"JobRunner error: {e}")
            time.sleep(2)

    def _resume_incomplete_consultations(self):
        """Find any queued or partially-done consultations and mark them active."""
        consultations = list_consultations()
        for c in consultations:
            if c["status"] in ("queued", "processing"):
                logger.info(f"Resuming consultation {c['id'][:8]} ({c['name']})")

    def _process_next(self):
        """Find the next queued consultation and process its utterances."""
        consultations = list_consultations()

        for c in consultations:
            if c["status"] not in ("queued", "processing"):
                continue

            cid = c["id"]
            self.current_job = cid
            utterances = get_queued_utterances_for_consultation(cid)

            if not utterances:
                # All utterances done — finalize consultation
                self._finalize_consultation(cid)
                continue

            # Process utterances one by one
            update_consultation(cid, status="processing")
            for utt in utterances:
                if self._stop_event.is_set():
                    return
                self._process_utterance(c, utt)

            # After processing all, finalize
            remaining = get_queued_utterances_for_consultation(cid)
            if not remaining:
                self._finalize_consultation(cid)

            self.current_job = None
            return  # Process one consultation per loop iteration

    def _process_utterance(self, consultation: dict, utterance: dict):
        uid = utterance["id"]
        cid = utterance["consultation_id"]
        text = utterance["text"]
        speaker = utterance["speaker"]
        engine = utterance.get("engine") or consultation.get("engine", "parler")
        language = utterance.get("language") or consultation.get("language", "hi")
        seed = consultation.get("seed")

        logger.info(f"  Generating: [{speaker}] '{text[:60]}...' (engine={engine})")
        update_utterance(uid, status="processing")

        try:
            # Determine output path
            output_dir = OUTPUTS_DIR / cid
            output_dir.mkdir(parents=True, exist_ok=True)
            idx = utterance.get("sort_order", 0)
            speaker_safe = speaker.replace(" ", "_")
            audio_filename = f"{idx:03d}_{speaker_safe}.mp3"
            audio_path = output_dir / audio_filename

            # Speaker voice settings from consultation
            speaker_settings = consultation.get("speaker_settings") or {}
            sp_settings = speaker_settings.get(speaker, {})
            gender = sp_settings.get("gender", "male")
            age = sp_settings.get("age", "adult")
            voice_description = sp_settings.get("voice_description") or utterance.get("voice_description")
            ref_audio_path = sp_settings.get("ref_audio_path") or utterance.get("ref_audio_path")
            ref_text = sp_settings.get("ref_text") or utterance.get("ref_text")

            # Add random variation to seed so each utterance differs slightly
            utt_seed = None
            if seed is not None:
                utt_seed = (seed + hash(uid)) % (2**31)

            t0 = time.time()
            audio_arr, sr = generate_speech(
                text=text,
                engine=engine,
                speaker=speaker,
                gender=gender,
                age=age,
                language=language,
                voice_description=voice_description,
                ref_audio_path=ref_audio_path,
                ref_text=ref_text,
                seed=utt_seed,
                output_path=audio_path,
            )
            elapsed = time.time() - t0
            duration = len(audio_arr) / sr

            # Apply noise if enabled
            noise_settings = consultation.get("noise_settings") or {}
            if noise_settings.get("enabled"):
                noisy_path = output_dir / f"{idx:03d}_{speaker_safe}_noisy.mp3"
                mix_noise(audio_path, noisy_path, noise_settings, sample_rate=sr)

            update_utterance(
                uid,
                status="done",
                audio_path=str(audio_path),
                duration_seconds=duration,
                completed_at=datetime.utcnow().isoformat(),
            )

            # Update progress on consultation
            counts = count_utterances_by_status(cid)
            done = counts.get("done", 0)
            total = sum(counts.values())
            update_consultation(cid, completed_utterances=done, total_utterances=total)

            logger.info(
                f"  Done [{speaker}]: {duration:.1f}s audio, generated in {elapsed:.1f}s"
            )

        except Exception as e:
            logger.exception(f"Error generating utterance {uid}: {e}")
            update_utterance(uid, status="error", error_message=str(e))

    def _finalize_consultation(self, cid: str):
        """Concatenate all utterances into one file and save metadata."""
        try:
            utterances = get_utterances(cid)
            done_utts = [u for u in utterances if u.get("status") == "done" and u.get("audio_path")]
            error_utts = [u for u in utterances if u.get("status") == "error"]

            output_dir = OUTPUTS_DIR / cid

            if done_utts:
                # Concatenate all audio
                parts = []
                silence = np.zeros(int(0.3 * 16000), dtype=np.float32)  # 300ms silence between turns
                for utt in sorted(done_utts, key=lambda u: u.get("sort_order", 0)):
                    ap = utt.get("audio_path")
                    if ap and Path(ap).exists():
                        audio, sr = sf.read(ap)
                        if audio.ndim > 1:
                            audio = audio.mean(axis=1)
                        parts.append(audio.astype(np.float32))
                        parts.append(silence)

                if parts:
                    full_audio = np.concatenate(parts)
                    full_path = output_dir / "full_consultation.mp3"
                    sf.write(str(full_path), full_audio, sr)

            # Save metadata files
            consultation = get_consultation(cid)
            save_consultation_files(output_dir, consultation, utterances)

            final_status = "error" if error_utts and not done_utts else "done"
            update_consultation(cid, status=final_status)
            logger.info(f"Consultation {cid[:8]} finalized with status={final_status}")

        except Exception as e:
            logger.exception(f"Error finalizing consultation {cid}: {e}")
            update_consultation(cid, status="error", error_message=str(e))

    def get_progress(self, cid: str) -> dict:
        utterances = get_utterances(cid)
        counts = count_utterances_by_status(cid)
        total = len(utterances)
        done = counts.get("done", 0)
        errored = counts.get("error", 0)
        processing = counts.get("processing", 0)
        return {
            "total": total,
            "done": done,
            "error": errored,
            "processing": processing,
            "queued": counts.get("queued", 0),
            "percent": round(done / total * 100) if total else 0,
            "is_current": self.current_job == cid,
        }


# Singleton runner instance
_runner: Optional[JobRunner] = None


def get_runner() -> JobRunner:
    global _runner
    return _runner


def start_runner():
    global _runner
    if _runner is None or not _runner.is_alive():
        _runner = JobRunner()
        _runner.start()
        logger.info("Job runner started")
    return _runner
