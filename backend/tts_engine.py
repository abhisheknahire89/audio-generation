"""
TTS Engine wrappers for Indic-Parler-TTS and IndicF5.
Both engines are loaded once and reused across requests.
Device auto-detection: mps -> cuda -> cpu
"""
import os
import time
import logging
import random
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# ─── Device selection ─────────────────────────────────────────────────────────

def get_device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


# ─── Voice profiles ───────────────────────────────────────────────────────────

SPEAKER_VOICE_PROFILES = {
    # (speaker_key, gender, age_group) → Parler description
    "doctor_male_adult": (
        "A middle-aged Indian male doctor with a calm, authoritative voice. "
        "Speaks at a moderate pace with clear Hindi-English pronunciation. "
        "Slightly tired but reassuring tone. Minimal background noise."
    ),
    "doctor_female_adult": (
        "A young Indian female doctor with a warm, professional voice. "
        "Speaks clearly and steadily with a slight South Indian accent. "
        "High quality recording."
    ),
    "patient_male_elderly": (
        "An elderly Indian male patient speaking slowly with slight hoarseness. "
        "Occasionally hesitates and repeats words. Concerned and worried tone. "
        "Speaks Hindi with a rural accent. Clear recording."
    ),
    "patient_female_adult": (
        "A young Indian woman speaking quickly with anxiety. "
        "Mumbai accent, mixes Hindi and English. Slightly breathless. "
        "Good recording quality."
    ),
    "patient_male_adult": (
        "A middle-aged Indian man speaking at normal pace. "
        "Slight UP accent, polite tone. Good recording quality."
    ),
    "patient_female_elderly": (
        "An elderly Indian woman speaking slowly and clearly. "
        "Traditional Hindi, calm but worried. Clear recording."
    ),
    "nurse_female_adult": (
        "An Indian female nurse speaking briskly and professionally. "
        "Clear diction, moderate pace, helpful tone. High quality."
    ),
    "attendant_male_adult": (
        "A middle-aged Indian man speaking with worry. "
        "Rural accent, speaks a bit fast when anxious. Good recording."
    ),
    "relative_female_adult": (
        "An Indian woman speaking with concern and emotion. "
        "Mixes Hindi and English, moderate pace. Clear recording."
    ),
    "receptionist_female_adult": (
        "An Indian female receptionist speaking professionally and clearly. "
        "Polite, measured pace, clinical tone. High quality recording."
    ),
    "default_male": (
        "An Indian male speaker with a clear, neutral voice. "
        "Moderate pace, good recording quality."
    ),
    "default_female": (
        "An Indian female speaker with a clear, neutral voice. "
        "Moderate pace, good recording quality."
    ),
}


def get_voice_profile(speaker: str, gender: str = "male", age: str = "adult", language: str = "hi") -> str:
    sp_lower = speaker.lower().replace(" ", "_")
    key = f"{sp_lower}_{gender}_{age}"
    profile = ""
    if key in SPEAKER_VOICE_PROFILES:
        profile = SPEAKER_VOICE_PROFILES[key]
    else:
        # Fuzzy match on speaker role
        for known_key, prof in SPEAKER_VOICE_PROFILES.items():
            if sp_lower in known_key:
                profile = prof
                break
        if not profile:
            profile = SPEAKER_VOICE_PROFILES[f"default_{gender}"]

    # Customize the accent based on the language
    if language != "hi":
        accents = {
            "hi_en": "Hindi-English code-switched",
            "mr_en": "Marathi-English code-switched",
            "gu": "Gujarati",
            "gu_en": "Gujarati-English code-switched",
            "te": "Telugu",
            "te_en": "Telugu-English code-switched"
        }
        accent = accents.get(language, "Hindi-English code-switched")
        # Replace accent terms in the profile
        profile = profile.replace("Hindi-English pronunciation", f"{accent} pronunciation")
        profile = profile.replace("Hindi-English", f"{accent}")
        profile = profile.replace("Hindi with a rural accent", f"{accent} accent")
        profile = profile.replace("traditional Hindi", f"traditional phrasing with a {accent} accent")
        profile = profile.replace("Hindi and English", f"{accent}")
    return profile


def get_random_voice_profile(speaker: str, gender: str = "male", age: str = "adult", language: str = "hi") -> str:
    # Generate pacing and quality variations dynamically
    pacings = [
        "Speaks at a moderate pace",
        "Speaks at a steady pace",
        "Speaks slightly fast",
        "Speaks slowly and clearly",
        "Speaks with a natural cadence"
    ]
    pacing = random.choice(pacings)

    qualities = [
        "Clear recording, minimal background noise",
        "High quality studio recording",
        "Very clear recording with clean audio",
        "Professional microphone quality"
    ]
    quality = random.choice(qualities)

    is_doc = "doc" in speaker.lower() or "dr" in speaker.lower()
    doctor_tones = [
        'warm, professional and reassuring tone',
        'calm, authoritative tone',
        'reassuring but slightly tired tone',
        'helpful and polite tone'
    ]
    patient_tones = [
        'concerned and worried tone',
        'slightly anxious tone',
        'polite and soft tone',
        'normal tone'
    ]
    tone = random.choice(doctor_tones) if is_doc else random.choice(patient_tones)

    accents = {
        "hi": "Hindi-English code-switched",
        "hi_en": "Hindi-English code-switched",
        "mr_en": "Marathi-English code-switched",
        "gu": "Gujarati",
        "gu_en": "Gujarati-English code-switched",
        "te": "Telugu",
        "te_en": "Telugu-English code-switched"
    }
    accent = accents.get(language, "Hindi-English code-switched")

    return f"A {age} Indian {gender} speaker. {pacing} with a {tone}. Speaks with a clear {accent} accent. {quality}."


# ─── Reference clips for IndicF5 ──────────────────────────────────────────────

REF_CLIPS_DIR = Path(__file__).parent / "reference_clips"

SPEAKER_REF_CLIPS = {
    "doctor_male": "doctor_male_ref.wav",
    "doctor_female": "doctor_female_ref.wav",
    "patient_male_elderly": "patient_elderly_male_ref.wav",
    "patient_female": "patient_female_ref.wav",
    "default_male": "default_male_ref.wav",
    "default_female": "default_female_ref.wav",
}

def get_ref_clip(speaker: str, gender: str = "male") -> Tuple[Optional[Path], Optional[str]]:
    sp_lower = speaker.lower().replace(" ", "_")
    for key, filename in SPEAKER_REF_CLIPS.items():
        if sp_lower in key:
            path = REF_CLIPS_DIR / filename
            if path.exists():
                txt_path = path.with_suffix(".txt")
                ref_text = txt_path.read_text().strip() if txt_path.exists() else ""
                return path, ref_text
    # Default fallback
    key = f"default_{gender}"
    path = REF_CLIPS_DIR / SPEAKER_REF_CLIPS.get(key, "default_male_ref.wav")
    if path.exists():
        txt_path = path.with_suffix(".txt")
        ref_text = txt_path.read_text().strip() if txt_path.exists() else ""
        return path, ref_text
    return None, None


# ─── Indic-Parler-TTS ─────────────────────────────────────────────────────────

class IndicParlerTTS:
    _instance = None

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = get_device()
        self.sample_rate = 44100
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        logger.info(f"Loading Indic-Parler-TTS on device={self.device}")
        t0 = time.time()
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        # Use float32 on MPS (float16 not fully supported)
        dtype = torch.float32
        hf_token = os.environ.get("HF_TOKEN")
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(
            "ai4bharat/indic-parler-tts",
            torch_dtype=dtype,
            token=hf_token,
        ).to(self.device)
        self.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(
            "ai4bharat/indic-parler-tts",
            token=hf_token,
        )
        self.sample_rate = self.model.config.sampling_rate
        self.loaded = True
        logger.info(f"Indic-Parler-TTS loaded in {time.time()-t0:.1f}s on {self.device}")

    def generate(
        self,
        text: str,
        description: str,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Tuple[np.ndarray, int]:
        import torch
        self.load()
        if seed is not None:
            torch.manual_seed(seed)
            random.seed(seed)
            np.random.seed(seed)

        input_ids = self.tokenizer(description, return_tensors="pt").input_ids.to(self.device)
        prompt_ids = self.tokenizer(text, return_tensors="pt").input_ids.to(self.device)

        with torch.no_grad():
            generation = self.model.generate(
                input_ids=input_ids,
                prompt_input_ids=prompt_ids,
            )

        audio = generation.cpu().numpy().squeeze()
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        # Normalize
        max_val = np.abs(audio).max()
        if max_val > 0:
            audio = audio / max_val * 0.9

        if output_path:
            sf.write(str(output_path), audio, self.sample_rate)

        return audio, self.sample_rate

    def generate_batch(
        self,
        texts: list,
        description: str,
        seed: Optional[int] = None,
    ) -> list:
        import torch
        self.load()
        if seed is not None:
            torch.manual_seed(seed)
            random.seed(seed)
            np.random.seed(seed)

        input_ids = self.tokenizer([description]*len(texts), return_tensors="pt", padding=True).input_ids.to(self.device)
        prompt_ids = self.tokenizer(texts, return_tensors="pt", padding=True).input_ids.to(self.device)

        with torch.no_grad():
            generation = self.model.generate(
                input_ids=input_ids,
                prompt_input_ids=prompt_ids,
            )

        audios = generation.cpu().numpy()
        results = []
        for i in range(audios.shape[0]):
            audio = audios[i].squeeze()
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.9
            results.append(audio)
        return results

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = IndicParlerTTS()
        return cls._instance


# ─── IndicF5 ──────────────────────────────────────────────────────────────────

class IndicF5Engine:
    _instance = None

    def __init__(self):
        self.model = None
        self.device = get_device()
        self.sample_rate = 24000
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        logger.info(f"Loading IndicF5 on device={self.device}")
        t0 = time.time()
        from transformers import AutoModel
        import torch

        hf_token = os.environ.get("HF_TOKEN")
        self.model = AutoModel.from_pretrained(
            "ai4bharat/IndicF5",
            trust_remote_code=True,
            token=hf_token,
        )
        # Move to device if possible
        if hasattr(self.model, "to"):
            try:
                self.model = self.model.to(self.device)
            except Exception:
                self.device = "cpu"
        self.model.eval()
        self.loaded = True
        logger.info(f"IndicF5 loaded in {time.time()-t0:.1f}s on {self.device}")

    def generate(
        self,
        text: str,
        ref_audio_path: str,
        ref_text: str,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Tuple[np.ndarray, int]:
        import torch
        self.load()
        if seed is not None:
            torch.manual_seed(seed)
            np.random.seed(seed)

        with torch.no_grad():
            audio = self.model(
                text,
                ref_audio_path=str(ref_audio_path),
                ref_text=ref_text,
            )

        if isinstance(audio, (list, tuple)):
            audio = np.array(audio[0] if len(audio) > 0 else audio, dtype=np.float32)
        else:
            audio = np.array(audio, dtype=np.float32)

        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        max_val = np.abs(audio).max()
        if max_val > 0:
            audio = audio / max_val * 0.9

        if output_path:
            sf.write(str(output_path), audio, self.sample_rate)

        return audio, self.sample_rate

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = IndicF5Engine()
        return cls._instance


# ─── Unified engine interface ─────────────────────────────────────────────────

def generate_speech(
    text: str,
    engine: str = "parler",
    speaker: str = "Doctor",
    gender: str = "male",
    age: str = "adult",
    language: str = "hi",
    voice_description: Optional[str] = None,
    ref_audio_path: Optional[str] = None,
    ref_text: Optional[str] = None,
    seed: Optional[int] = None,
    output_path: Optional[Path] = None,
) -> Tuple[np.ndarray, int]:
    """
    Unified TTS call. Returns (audio_array, sample_rate).
    """
    import re
    from transliteration import transliterate_hinglish_sentence
    
    def chunk_text(text: str, max_words: int = 35) -> List[str]:
        sentences = re.split(r'([.?!।|]+)', text)
        chunks = []
        current_chunk = ""
        for i in range(0, len(sentences)-1, 2):
            s = (sentences[i] + sentences[i+1]).strip()
            if not s: continue
            if len(current_chunk.split()) + len(s.split()) > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = s
            else:
                current_chunk += " " + s
        if sentences[-1].strip():
            s = sentences[-1].strip()
            if len(current_chunk.split()) + len(s.split()) > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                chunks.append(s)
            else:
                current_chunk += " " + s
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        if not chunks and text.strip():
            chunks = [text]
            
        final_chunks = []
        for c in chunks:
            words = c.split()
            while len(words) > max_words:
                final_chunks.append(" ".join(words[:max_words]))
                words = words[max_words:]
            if words:
                final_chunks.append(" ".join(words))
        return final_chunks

    orig_text = text
    if language in ("hi", "hi_en", "mr_en", "gu", "gu_en", "te", "te_en"):
        text = transliterate_hinglish_sentence(text, language)
        if text != orig_text:
            logger.info(f"Transliterated [{language}]: '{orig_text}' -> '{text}'")

    chunks = chunk_text(text)
    audio_parts = []
    sample_rate = 24000 if engine == "indicf5" else 44100
    
    if engine == "parler":
        # Batch generation for Parler
        desc = voice_description or get_voice_profile(speaker, gender, age, language)
        eng = IndicParlerTTS.get_instance()
        sample_rate = eng.sample_rate or 44100
        
        # Process in batches of 4
        batch_size = 4
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            logger.info(f"Generating Parler batch {i//batch_size + 1}: {len(batch)} chunks")
            batch_audios = eng.generate_batch(batch, desc, seed=seed)
            for j, audio_arr in enumerate(batch_audios):
                audio_parts.append(audio_arr)
                if i + j < len(chunks) - 1:
                    pause = np.zeros(int(0.3 * sample_rate), dtype=np.float32)
                    audio_parts.append(pause)
    else:
        for i, chunk in enumerate(chunks):
            logger.info(f"Generating chunk {i+1}/{len(chunks)}: {chunk}")
            if ref_audio_path and Path(ref_audio_path).exists():
                rpath = ref_audio_path
                rtext = ref_text or ""
            else:
                rpath, rtext = get_ref_clip(speaker, gender)
                if rpath is None:
                    logger.warning("No ref clip found for IndicF5, falling back to Parler")
                    eng = IndicParlerTTS.get_instance()
                    desc = voice_description or get_voice_profile(speaker, gender, age, language)
                    audio_arr, sr = eng.generate(chunk, desc, seed=seed, output_path=None)
                    sample_rate = sr
                else:
                    eng = IndicF5Engine.get_instance()
                    audio_arr, sr = eng.generate(chunk, str(rpath), rtext, seed=seed, output_path=None)
                    sample_rate = sr
            
            audio_parts.append(audio_arr)
            # Add a short 300ms pause between sentences within the same turn
            if i < len(chunks) - 1:
                pause = np.zeros(int(0.3 * sample_rate), dtype=np.float32)
                audio_parts.append(pause)
            
    final_audio = np.concatenate(audio_parts) if audio_parts else np.zeros(sample_rate, dtype=np.float32)
    
    if output_path:
        import soundfile as sf
        sf.write(str(output_path), final_audio, sample_rate)
        
    return final_audio, sample_rate


def check_engine_availability() -> dict:
    """Quick check — does not load models, just checks imports."""
    status = {"parler": False, "indicf5": False, "device": get_device()}
    try:
        import parler_tts  # noqa
        status["parler"] = True
    except ImportError:
        pass
    try:
        import transformers  # noqa
        status["indicf5"] = True  # IndicF5 uses transformers
    except ImportError:
        pass
    return status
