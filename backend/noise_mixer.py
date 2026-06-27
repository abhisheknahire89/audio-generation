"""
Noise mixer: overlay clinic background noise on top of clean speech WAV.
Uses pydub for mixing. Noise clips are generated synthetically if not present.
"""
import logging
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

NOISE_DIR = Path(__file__).parent.parent / "noise_samples"

NOISE_TYPES = {
    "hospital_ambience": "hospital_ambience.wav",
    "fan": "fan_hum.wav",
    "ac": "ac_hum.wav",
    "keyboard": "keyboard_typing.wav",
    "phone": "phone_ring.wav",
    "cough": "coughing.wav",
    "door": "door_sounds.wav",
    "chatter": "nearby_chatter.wav",
    "opd_mix": "opd_mix.wav",
}


def _generate_pink_noise(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Generate pink noise (1/f) approximation."""
    n = int(duration_s * sample_rate)
    white = np.random.randn(n)
    # Pink noise via FFT filtering
    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1  # avoid div by zero
    fft = np.fft.rfft(white)
    pink_fft = fft / np.sqrt(freqs)
    pink = np.fft.irfft(pink_fft, n=n)
    pink = pink / np.abs(pink).max() * 0.3
    return pink.astype(np.float32)


def _generate_hum(frequency: float, duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Generate a steady electrical/mechanical hum."""
    t = np.linspace(0, duration_s, int(duration_s * sample_rate), endpoint=False)
    hum = (
        0.3 * np.sin(2 * np.pi * frequency * t)
        + 0.15 * np.sin(2 * np.pi * frequency * 2 * t)
        + 0.08 * np.sin(2 * np.pi * frequency * 3 * t)
    )
    hum = hum / np.abs(hum).max() * 0.25
    return hum.astype(np.float32)


def _generate_keyboard(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Simulate keyboard clicking."""
    n = int(duration_s * sample_rate)
    audio = np.zeros(n, dtype=np.float32)
    clicks_per_sec = 4.0
    for click_time in np.arange(0, duration_s, 1 / clicks_per_sec):
        if np.random.random() > 0.3:
            pos = int(click_time * sample_rate)
            click_len = int(0.01 * sample_rate)
            if pos + click_len < n:
                click = np.random.randn(click_len).astype(np.float32)
                click *= np.exp(-np.linspace(0, 5, click_len))
                audio[pos:pos + click_len] += click * 0.4
    return audio


def _generate_cough(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Simulate occasional coughing sounds."""
    n = int(duration_s * sample_rate)
    audio = np.zeros(n, dtype=np.float32)
    cough_positions = np.random.uniform(0, duration_s, max(1, int(duration_s / 8)))
    for t in cough_positions:
        pos = int(t * sample_rate)
        cough_len = int(0.3 * sample_rate)
        if pos + cough_len < n:
            cough = np.random.randn(cough_len).astype(np.float32)
            env = np.concatenate([
                np.linspace(0, 1, cough_len // 4),
                np.linspace(1, 0, cough_len - cough_len // 4),
            ])
            audio[pos:pos + cough_len] += cough * env * 0.5
    return audio


def _generate_chatter(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Simulate muffled background chatter."""
    pink = _generate_pink_noise(duration_s, sample_rate)
    # Apply bandpass-like weighting: emphasize speech frequencies
    t = np.linspace(0, duration_s, len(pink))
    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t + np.random.random() * 2 * np.pi)
    return (pink * modulation * 0.4).astype(np.float32)


def _generate_phone_ring(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Simulate a phone ringing occasionally."""
    n = int(duration_s * sample_rate)
    audio = np.zeros(n, dtype=np.float32)
    if duration_s > 5 and np.random.random() > 0.5:
        t_ring = np.random.uniform(2, duration_s - 3)
        pos = int(t_ring * sample_rate)
        ring_len = int(1.5 * sample_rate)
        if pos + ring_len < n:
            t = np.linspace(0, 1.5, ring_len)
            ring = np.sin(2 * np.pi * 900 * t) * np.sin(2 * np.pi * 2.5 * t)
            audio[pos:pos + ring_len] += ring.astype(np.float32) * 0.3
    return audio


def generate_noise_clips():
    """Generate all noise WAV clips and save to NOISE_DIR."""
    NOISE_DIR.mkdir(parents=True, exist_ok=True)
    sr = 16000
    duration = 30.0  # 30 seconds each, will be looped as needed

    clips = {
        "hospital_ambience.wav": _generate_pink_noise(duration, sr) * 0.5 + _generate_chatter(duration, sr),
        "fan_hum.wav": _generate_hum(120, duration, sr),
        "ac_hum.wav": _generate_hum(60, duration, sr) + _generate_pink_noise(duration, sr) * 0.15,
        "keyboard_typing.wav": _generate_keyboard(duration, sr),
        "phone_ring.wav": _generate_phone_ring(duration, sr),
        "coughing.wav": _generate_cough(duration, sr),
        "door_sounds.wav": _generate_cough(duration, sr) * 0.3 + np.random.randn(int(duration * sr)).astype(np.float32) * 0.02,
        "nearby_chatter.wav": _generate_chatter(duration, sr),
        "opd_mix.wav": (
            _generate_pink_noise(duration, sr) * 0.3
            + _generate_hum(60, duration, sr) * 0.15
            + _generate_chatter(duration, sr) * 0.4
            + _generate_keyboard(duration, sr) * 0.2
        ),
    }

    for filename, audio in clips.items():
        path = NOISE_DIR / filename
        if not path.exists():
            # Normalize
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.7
            sf.write(str(path), audio.astype(np.float32), sr)
            logger.info(f"Generated noise clip: {filename}")


def _load_noise(noise_type: str, target_len: int, sample_rate: int) -> Optional[np.ndarray]:
    """Load a noise clip and loop/trim to match target_len at sample_rate."""
    filename = NOISE_TYPES.get(noise_type)
    if not filename:
        return None
    path = NOISE_DIR / filename
    if not path.exists():
        generate_noise_clips()
    if not path.exists():
        return None

    noise, sr = sf.read(str(path))
    if noise.ndim > 1:
        noise = noise.mean(axis=1)
    noise = noise.astype(np.float32)

    # Resample if needed
    if sr != sample_rate:
        duration = len(noise) / sr
        target_len_noise = int(duration * sample_rate)
        src_indices = np.linspace(0, len(noise) - 1, len(noise))
        target_indices = np.linspace(0, len(noise) - 1, target_len_noise)
        noise = np.interp(target_indices, src_indices, noise).astype(np.float32)

    # Loop/trim to match target_len
    if len(noise) < target_len:
        repeats = (target_len // len(noise)) + 1
        noise = np.tile(noise, repeats)
    noise = noise[:target_len]
    return noise


def mix_noise(
    speech_path: Path,
    output_path: Path,
    noise_settings: Dict,
    sample_rate: int = 16000,
) -> Path:
    """
    Mix enabled noise types on top of clean speech.
    noise_settings = {
        "enabled": bool,
        "types": {"fan": True, "ac": False, ...},
        "intensity": 0.0–1.0,   # overall noise level
    }
    Returns output_path (same as input if no noise enabled).
    """
    if not noise_settings.get("enabled", False):
        return speech_path

    speech, sr = sf.read(str(speech_path))
    if speech.ndim > 1:
        speech = speech.mean(axis=1)
    speech = speech.astype(np.float32)

    intensity = float(noise_settings.get("intensity", 0.3))
    active_types = [k for k, v in noise_settings.get("types", {}).items() if v]

    if not active_types:
        return speech_path

    noise_mix = np.zeros_like(speech)
    for noise_type in active_types:
        noise = _load_noise(noise_type, len(speech), sr)
        if noise is not None:
            noise_mix += noise / len(active_types)

    # Normalize noise mix
    max_noise = np.abs(noise_mix).max()
    if max_noise > 0:
        noise_mix = noise_mix / max_noise

    # Mix: speech and noise at intensity
    mixed = speech + noise_mix * intensity
    
    # Normalize the final mix to 0.95 to prevent any clipping distortion
    max_mixed = np.abs(mixed).max()
    if max_mixed > 0:
        mixed = (mixed / max_mixed) * 0.95

    sf.write(str(output_path), mixed, sr)
    logger.info(f"Mixed noise ({active_types}) at intensity={intensity} -> {output_path}")
    return output_path

