#!/usr/bin/env python3
"""
Generate synthetic reference voice clips for IndicF5.
These are simple harmonic signals that approximate different voice types.
For best results, replace with real 3-5 second voice recordings.
Run: python generate_reference_clips.py
"""
import numpy as np
import soundfile as sf
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "backend" / "reference_clips"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SR = 24000  # IndicF5 sample rate

def make_voice(freq_hz: float, duration: float = 4.0, vibrato: float = 5.0, jitter: float = 0.002) -> np.ndarray:
    """Synthesize a simple vowel-like reference signal."""
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    
    # Vibrato modulation
    vib = 1 + 0.003 * np.sin(2 * np.pi * vibrato * t)
    
    # Fundamental + harmonics (rough voice approximation)
    signal = (
        0.4 * np.sin(2 * np.pi * freq_hz * vib * t)
        + 0.25 * np.sin(2 * np.pi * freq_hz * 2 * vib * t)
        + 0.15 * np.sin(2 * np.pi * freq_hz * 3 * vib * t)
        + 0.1 * np.sin(2 * np.pi * freq_hz * 4 * vib * t)
        + 0.05 * np.sin(2 * np.pi * freq_hz * 5 * vib * t)
    )
    
    # Add small jitter (pitch variation)
    noise = np.random.randn(len(t)) * jitter
    signal = signal + noise * 0.1
    
    # Apply envelope
    env = np.ones(len(t))
    fade_len = int(0.05 * SR)
    env[:fade_len] = np.linspace(0, 1, fade_len)
    env[-fade_len:] = np.linspace(1, 0, fade_len)
    signal = signal * env
    
    # Normalize
    max_val = np.abs(signal).max()
    if max_val > 0:
        signal = signal / max_val * 0.7
    
    return signal.astype(np.float32)


clips = [
    # (filename, ref_text, fundamental_freq_hz, description)
    ("doctor_male_ref.wav",
     "Namaste, main aapka doctor hun. Aaj aap kaise feel kar rahe hain?",
     120.0,
     "Middle-aged male doctor voice, 120 Hz fundamental"),
    
    ("doctor_female_ref.wav",
     "Hello, main Dr. Sharma hun. Aapko kya problem hai aaj?",
     220.0,
     "Young female doctor voice, 220 Hz fundamental"),
    
    ("patient_elderly_male_ref.wav",
     "Doctor sahab, teen din se bukhar hai. Bohot kamzori lag rahi hai.",
     100.0,
     "Elderly male patient voice, 100 Hz fundamental"),
    
    ("patient_female_ref.wav",
     "Doctor ji, mere pet mein dard ho raha hai subah se.",
     250.0,
     "Young female patient voice, 250 Hz fundamental"),
    
    ("default_male_ref.wav",
     "Acha doctor sahab, theek hai. Main samajh gaya.",
     130.0,
     "Default male voice"),
    
    ("default_female_ref.wav",
     "Ji haan, main dekhungi. Koi baat nahi.",
     210.0,
     "Default female voice"),
]

print("Generating reference clips for IndicF5...")
for filename, ref_text, freq, desc in clips:
    path = OUTPUT_DIR / filename
    audio = make_voice(freq)
    sf.write(str(path), audio, SR)
    
    # Save reference text
    txt_path = path.with_suffix(".txt")
    txt_path.write_text(ref_text)
    
    print(f"  ✓ {filename} ({desc})")

print(f"\nDone. Clips saved to: {OUTPUT_DIR}")
print("\nNOTE: These are synthetic approximations.")
print("For better voice cloning with IndicF5, replace these with real 3-5s voice recordings.")
print("Each WAV should have a matching .txt file with the transcript of what was said.")
