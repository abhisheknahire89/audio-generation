import time
import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from tts_engine import IndicParlerTTS, IndicF5Engine, get_device

print("Device:", get_device())

text = "આજે મને સારું લાગતું નથી, કદાચ તાવ આવી રહ્યો છે."

def bench_parler():
    eng = IndicParlerTTS.get_instance()
    eng.load()
    t0 = time.time()
    eng.generate(text, "A healthy adult male speaking calmly", None)
    t1 = time.time()
    return t1 - t0

def bench_f5():
    eng = IndicF5Engine.get_instance()
    eng.load()
    t0 = time.time()
    try:
        # F5 needs ref clip. We will just use the default.
        from tts_engine import get_ref_clip
        rpath, rtext = get_ref_clip("Doctor", "male")
        if rpath:
            eng.generate(text, str(rpath), rtext, None)
    except Exception as e:
        print("F5 generation error:", e)
    t1 = time.time()
    return t1 - t0

# Warmup to ignore load time
print("Warming up Parler...")
bench_parler()
print("Benchmarking Parler...")
pt = bench_parler()
print(f"Parler time: {pt:.2f}s")

try:
    print("Warming up F5...")
    bench_f5()
    print("Benchmarking F5...")
    ft = bench_f5()
    print(f"F5 time: {ft:.2f}s")
except Exception as e:
    print("F5 failed to run:", e)
