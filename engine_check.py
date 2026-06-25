#!/usr/bin/env python3
"""
Phase 0 — Engine Check Script
Tests both Indic-Parler-TTS and IndicF5 on 3 sample utterances.
Reports quality assessment and generation time.
Run: python engine_check.py
"""
import sys
import time
import json
from pathlib import Path

# Add backend to path for transliteration helper
sys.path.insert(0, str(Path(__file__).parent / "backend"))

OUTPUT_DIR = Path(__file__).parent / "engine_check_output"
OUTPUT_DIR.mkdir(exist_ok=True)

TEST_UTTERANCES = [
    {
        "id": "hindi",
        "text": "नमस्ते। आपको कितने दिनों से बुखार है? क्या सिरदर्द भी हो रहा है?",
        "language": "hi",
        "speaker": "Doctor",
        "description": "Hindi — Doctor asking about fever"
    },
    {
        "id": "hinglish",
        "text": "Doctor sahab, teen din se fever hai. Temperature 102 pe hai. Bohot weakness feel ho rahi hai.",
        "language": "hi",
        "speaker": "Patient",
        "description": "Hinglish — Patient describing symptoms"
    },
    {
        "id": "marathi",
        "text": "डॉक्टर, माझ्या आईला दोन दिवसांपासून छाती दुखत आहे. श्वास घ्यायला त्रास होतो आहे.",
        "language": "mr",
        "speaker": "Relative",
        "description": "Marathi — Relative describing chest pain"
    },
]

PARLER_DESCRIPTIONS = {
    "Doctor": "A middle-aged Indian male doctor with a calm, authoritative voice. Speaks at a moderate pace. Clear Hindi-English pronunciation. Minimal background noise.",
    "Patient": "A young Indian woman speaking with slight anxiety. Mixes Hindi and English. Slightly breathless. Good recording quality.",
    "Relative": "A middle-aged Indian woman speaking with concern. Marathi accent, moderate pace. Clear recording.",
}

results = {
    "parler": {"success": False, "times": [], "error": None, "files": []},
    "indicf5": {"success": False, "times": [], "error": None, "files": []},
    "device": None,
}


def test_parler():
    print("\n" + "="*60)
    print("Testing: Indic-Parler-TTS")
    print("="*60)

    try:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        import soundfile as sf
        import numpy as np

        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        results["device"] = device
        print(f"Device: {device}")

        print("Loading model (this may take a few minutes on first run)...")
        t_load = time.time()
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            "ai4bharat/indic-parler-tts",
            torch_dtype=torch.float32,
        ).to(device)
        tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
        print(f"Model loaded in {time.time()-t_load:.1f}s")

        for utt in TEST_UTTERANCES:
            print(f"\n  Generating [{utt['description']}]...")
            description = PARLER_DESCRIPTIONS.get(utt["speaker"], PARLER_DESCRIPTIONS["Doctor"])
            t0 = time.time()

            text = utt["text"]
            if utt["language"] == "hi":
                from transliteration import transliterate_hinglish_sentence
                text = transliterate_hinglish_sentence(text)
                print(f"    Transliterated text: '{utt['text']}' -> '{text}'")

            input_ids = tokenizer(description, return_tensors="pt").input_ids.to(device)
            prompt_ids = tokenizer(text, return_tensors="pt").input_ids.to(device)
            with torch.no_grad():
                generation = model.generate(input_ids=input_ids, prompt_input_ids=prompt_ids)

            audio = generation.cpu().numpy().squeeze().astype(np.float32)
            sr = model.config.sampling_rate
            elapsed = time.time() - t0
            duration = len(audio) / sr

            out_path = OUTPUT_DIR / f"parler_{utt['id']}.wav"
            sf.write(str(out_path), audio, sr)
            results["parler"]["times"].append(elapsed)
            results["parler"]["files"].append(str(out_path))

            rtf = elapsed / duration  # real-time factor (lower = faster)
            print(f"  ✓ Done: {duration:.1f}s audio in {elapsed:.1f}s (RTF={rtf:.2f}) → {out_path.name}")

        results["parler"]["success"] = True
        print("\n  Indic-Parler-TTS: SUCCESS ✓")

    except ImportError as e:
        results["parler"]["error"] = f"Import error: {e}"
        print(f"  ✗ Indic-Parler-TTS not installed: {e}")
        print("  Install with: pip install git+https://github.com/huggingface/parler-tts.git")
    except Exception as e:
        results["parler"]["error"] = str(e)
        print(f"  ✗ Indic-Parler-TTS failed: {e}")


def test_indicf5():
    print("\n" + "="*60)
    print("Testing: IndicF5")
    print("="*60)

    ref_clips_dir = Path(__file__).parent / "backend" / "reference_clips"
    ref_clips = list(ref_clips_dir.glob("*.wav"))

    if not ref_clips:
        print("  ✗ No reference clips found in backend/reference_clips/")
        print("  IndicF5 requires a short voice reference WAV. Skipping.")
        results["indicf5"]["error"] = "No reference clips"
        return

    ref_audio = str(ref_clips[0])
    ref_txt = Path(ref_audio).with_suffix(".txt")
    ref_text = ref_txt.read_text().strip() if ref_txt.exists() else "Hello, this is a test recording."

    try:
        import os
        from transformers import AutoModel
        import soundfile as sf
        import numpy as np
        import torch

        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        hf_token = os.environ.get("HF_TOKEN")

        print(f"HF_TOKEN present: {'Yes' if hf_token else 'No (may fail for gated model)'}")
        print("Loading IndicF5 model...")

        t_load = time.time()
        model = AutoModel.from_pretrained(
            "ai4bharat/IndicF5",
            trust_remote_code=True,
            token=hf_token,
        )
        print(f"Model loaded in {time.time()-t_load:.1f}s")

        for utt in TEST_UTTERANCES[:2]:  # Only test first 2 (slower model)
            print(f"\n  Generating [{utt['description']}]...")
            t0 = time.time()

            text = utt["text"]
            if utt["language"] == "hi":
                from transliteration import transliterate_hinglish_sentence
                text = transliterate_hinglish_sentence(text)
                print(f"    Transliterated text: '{utt['text']}' -> '{text}'")

            audio = model(
                text,
                ref_audio_path=ref_audio,
                ref_text=ref_text,
            )
            audio = np.array(audio, dtype=np.float32)
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0

            elapsed = time.time() - t0
            sr = 24000
            duration = len(audio) / sr

            out_path = OUTPUT_DIR / f"indicf5_{utt['id']}.wav"
            sf.write(str(out_path), audio, sr)
            results["indicf5"]["times"].append(elapsed)
            results["indicf5"]["files"].append(str(out_path))

            rtf = elapsed / duration
            print(f"  ✓ Done: {duration:.1f}s audio in {elapsed:.1f}s (RTF={rtf:.2f}) → {out_path.name}")

        results["indicf5"]["success"] = True
        print("\n  IndicF5: SUCCESS ✓")

    except Exception as e:
        results["indicf5"]["error"] = str(e)
        print(f"  ✗ IndicF5 failed: {e}")
        if "gated" in str(e).lower() or "401" in str(e) or "403" in str(e):
            print("  → This is a gated model. Set HF_TOKEN to your Hugging Face token.")
            print("  → Accept the terms at: https://huggingface.co/ai4bharat/IndicF5")


def print_summary():
    print("\n" + "="*60)
    print("ENGINE CHECK SUMMARY")
    print("="*60)

    def avg(lst):
        return sum(lst)/len(lst) if lst else None

    parler_ok = results["parler"]["success"]
    f5_ok = results["indicf5"]["success"]

    print(f"\nIndic-Parler-TTS:  {'✓ OK' if parler_ok else '✗ FAILED'}")
    if parler_ok:
        avg_t = avg(results["parler"]["times"])
        print(f"  Avg generation time: {avg_t:.1f}s per utterance")

    print(f"\nIndicF5:           {'✓ OK' if f5_ok else '✗ FAILED'}")
    if f5_ok:
        avg_t = avg(results["indicf5"]["times"])
        print(f"  Avg generation time: {avg_t:.1f}s per utterance")
    else:
        print(f"  Error: {results['indicf5']['error']}")

    print(f"\nDevice used: {results.get('device', 'unknown')}")

    if parler_ok:
        print("\n✅ RECOMMENDED DEFAULT ENGINE: Indic-Parler-TTS")
        print("   (Broader language support, no reference clip needed, faster on CPU/MPS)")
    elif f5_ok:
        print("\n✅ RECOMMENDED DEFAULT ENGINE: IndicF5")
    else:
        print("\n⚠️  Neither engine loaded successfully.")
        print("   Check that dependencies are installed. See SETUP.md.")

    # Save results
    out = OUTPUT_DIR / "engine_check_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed results saved to: {out}")
    print(f"Test audio files saved to: {OUTPUT_DIR}/")
    print("\nListen to the test files to verify audio quality before proceeding.")


if __name__ == "__main__":
    print("OPD Audio Generator — Engine Check")
    print("Testing AI4Bharat TTS engines on 3 sample Indian medical utterances")

    test_parler()
    test_indicf5()
    print_summary()
