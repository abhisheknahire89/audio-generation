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
from typing import Optional, List, Dict, Any

import numpy as np
import soundfile as sf

from database import (
    get_consultation, get_utterances, get_queued_utterances_for_consultation,
    list_consultations, update_consultation, update_utterance,
    count_utterances_by_status, reset_stuck_utterances,
    get_batch_job, list_batch_jobs, update_batch_job,
)
from noise_mixer import mix_noise
from tts_engine import generate_speech, generate_batch_speech, get_voice_profile
from zip_builder import save_consultation_files

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"


class JobRunner(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="JobRunner")
        self._stop_event = threading.Event()
        self.current_job: Optional[str] = None  # consultation_id being processed
        self._batch_size = 4  # Number of utterances to generate in one batch

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
        """
        Process all queued utterances across all consultations in batches.
        This maximises GPU utilisation by grouping utterances with the same
        voice description.
        """
        # 1. Gather all queued utterances from all consultations
        all_queued = []
        consultations = list_consultations()
        for c in consultations:
            if c["status"] not in ("queued", "processing"):
                continue
            utts = get_queued_utterances_for_consultation(c["id"])
            if utts:
                # Attach consultation data to each utterance for later use
                for u in utts:
                    u["_consultation"] = c
                all_queued.extend(utts)

        if not all_queued:
            # No queued utterances: finalise any consultations that are done
            for c in consultations:
                if c["status"] in ("queued", "processing"):
                    # Check if it has any queued utterances left
                    remaining = get_queued_utterances_for_consultation(c["id"])
                    if not remaining:
                        self._finalize_consultation(c["id"])
            return

        # 2. Group by (engine, language, voice_description) for batching
        groups: Dict[str, List[Dict]] = {}
        for utt in all_queued:
            consultation = utt["_consultation"]
            speaker = utt["speaker"]
            speaker_settings = consultation.get("speaker_settings", {})
            sp_cfg = speaker_settings.get(speaker, {})
            engine = sp_cfg.get("engine") or consultation.get("engine", "parler")
            language = sp_cfg.get("language") or consultation.get("language", "hi")
            # Build voice description
            voice_desc = utt.get("voice_description") or sp_cfg.get("voice_description")
            if not voice_desc:
                gender = sp_cfg.get("gender", "male")
                age = sp_cfg.get("age", "adult")
                voice_desc = get_voice_profile(speaker, gender, age, language)
            key = f"{engine}|{language}|{voice_desc}"
            groups.setdefault(key, []).append(utt)

        # 3. Process each group in batches
        for key, batch in groups.items():
            if self._stop_event.is_set():
                return
            engine, language, voice_desc = key.split("|", 2)
            # Process in sub-batches of size `self._batch_size`
            for i in range(0, len(batch), self._batch_size):
                if self._stop_event.is_set():
                    return
                sub_batch = batch[i:i+self._batch_size]
                self._process_utterance_batch(sub_batch, engine, language, voice_desc)

        # 4. After all utterances processed, finalise consultations that are done
        for c in consultations:
            if c["status"] in ("queued", "processing"):
                remaining = get_queued_utterances_for_consultation(c["id"])
                if not remaining:
                    self._finalize_consultation(c["id"])

    def _process_utterance_batch(self, utterances: List[Dict], engine: str, language: str, voice_desc: str):
        """
        Generate a batch of utterances using the TTS engine's batch generation.
        """
        if not utterances:
            return

        # Extract texts and metadata
        texts = [u["text"] for u in utterances]
        # Use the seed from the first consultation (or random)
        first_cons = utterances[0]["_consultation"]
        seed_base = first_cons.get("seed") or random.randint(1, 999999)
        # Deterministic seed per utterance to maintain consistency
        seeds = [seed_base + hash(u["id"]) % 100000 for u in utterances]

        logger.info(f"Generating batch of {len(utterances)} utterances (engine={engine}, lang={language})")

        try:
            # Generate audios in batch
            audios, sr = generate_batch_speech(
                texts=texts,
                engine=engine,
                speaker=utterances[0]["speaker"],  # only used for Parler description
                gender="male",  # will be overridden by voice_desc
                age="adult",
                language=language,
                voice_description=voice_desc,
                seeds=seeds,
            )

            # Save each audio and update DB
            for utt, audio in zip(utterances, audios):
                uid = utt["id"]
                cid = utt["consultation_id"]
                consultation = utt["_consultation"]
                speaker = utt["speaker"]

                output_dir = OUTPUTS_DIR / cid
                output_dir.mkdir(parents=True, exist_ok=True)
                idx = utt.get("sort_order", 0)
                speaker_safe = speaker.replace(" ", "_")
                audio_filename = f"{idx:03d}_{speaker_safe}.mp3"
                audio_path = output_dir / audio_filename

                # Save audio
                sf.write(str(audio_path), audio, sr)

                duration = len(audio) / sr

                # Apply noise if enabled
                noise_settings = consultation.get("noise_settings") or {}
                if noise_settings.get("enabled"):
                    noisy_path = output_dir / f"{idx:03d}_{speaker_safe}_noisy.mp3"
                    mix_noise(audio_path, noisy_path, noise_settings, sample_rate=sr)

                # Update utterance status
                update_utterance(
                    uid,
                    status="done",
                    audio_path=str(audio_path),
                    duration_seconds=duration,
                    completed_at=datetime.utcnow().isoformat(),
                )

                # Update consultation progress
                counts = count_utterances_by_status(cid)
                done = counts.get("done", 0)
                total = sum(counts.values())
                update_consultation(cid, completed_utterances=done, total_utterances=total)

                logger.info(f"  Done [{speaker}]: {duration:.1f}s audio")

        except Exception as e:
            logger.exception(f"Error generating batch: {e}")
            # Mark all utterances in this batch as error
            for utt in utterances:
                update_utterance(utt["id"], status="error", error_message=str(e))

    def _finalize_consultation(self, cid: str):
        """Concatenate all utterances into one file and save metadata."""
        try:
            utterances = get_utterances(cid)
            done_utts = [u for u in utterances if u.get("status") == "done" and u.get("audio_path")]
            error_utts = [u for u in utterances if u.get("status") == "error"]

            output_dir = OUTPUTS_DIR / cid

            if done_utts:
                parts = []
                silence = np.zeros(int(0.3 * 16000), dtype=np.float32)  # 300ms silence
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


def get_runner() -> Optional[JobRunner]:
    return _runner


def start_runner():
    global _runner
    if _runner is None or not _runner.is_alive():
        _runner = JobRunner()
        _runner.start()
        logger.info("Job runner started")
    return _runner


def stop_runner(runner: JobRunner):
    if runner:
        runner.stop()
        runner.join(timeout=10)
        logger.info("Job runner stopped")
