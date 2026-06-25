import json
import time
import httpx
import zipfile
import io

API_URL = "http://localhost:8000/api"
AUTH = ("admin", "opdaudio2026")

def test_e2e_randomization():
    print("==========================================")
    print("Starting E2E Randomization Integration Test")
    print("==========================================")

    # 1. Hitting the health check first (should not require authentication)
    print("1. Checking health endpoint...")
    r = httpx.get(f"{API_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    health = r.json()
    print(f"Health: status={health['status']}, engines={health['engines']}, device={health['engines']['device']}")

    # 2. Creating a consultation with randomize=True (simulating the associate's simple mode)
    print("\n2. Submitting consultation script in Simple Mode (randomize=True)...")
    script = (
        "Doctor: Hello, Arjun! Kaise ho beta?\n"
        "Patient: Doctor, kal raat se fever aur cold thayo che."
    )
    
    payload = {
        "name": "E2E Test Simple Mode",
        "script": script,
        "language": "gu_en",  # Gujarati + English
        "engine": "parler",
        "randomize": True
    }
    
    r = httpx.post(
        f"{API_URL}/consultations",
        data={"request_json": json.dumps(payload)},
        auth=AUTH
    )
    assert r.status_code == 200, f"Submission failed: {r.text}"
    resp = r.json()
    cid = resp["id"]
    seed = resp["seed"]
    print(f"Consultation created: id={cid}, seed={seed}, turns={resp['total_utterances']}")

    # 3. Reading consultation detail to verify randomized parameters
    print("\n3. Verifying randomized speaker & noise settings...")
    r = httpx.get(f"{API_URL}/consultations/{cid}", auth=AUTH)
    assert r.status_code == 200
    details = r.json()

    print(f"DB Saved Language: {details['language']}")
    assert details["language"] == "gu_en"

    noise_settings = details["noise_settings"]
    print(f"Randomized Noise Settings: enabled={noise_settings.get('enabled')}, intensity={noise_settings.get('intensity')}")
    print(f"Active Noise types: {[k for k, v in noise_settings.get('types', {}).items() if v]}")
    
    # Assert that some noise types were chosen
    assert noise_settings.get("enabled") is True
    assert 0.15 <= noise_settings.get("intensity") <= 0.40
    assert any(noise_settings.get("types", {}).values())

    # Verify that the speaker settings got randomized
    speaker_settings = details["speaker_settings"]
    for sp, cfg in speaker_settings.items():
        print(f"Speaker '{sp}' config:")
        print(f"  Gender: {cfg.get('gender')}")
        print(f"  Age: {cfg.get('age')}")
        print(f"  Voice Description: {cfg.get('voice_description')}")
        assert cfg.get("gender") in ("male", "female")
        assert cfg.get("age") in ("adult", "elderly", "young")
        assert "Gujarati-English" in cfg.get("voice_description")

    # 4. Polling progress until complete
    print("\n4. Polling progress of background audio synthesis...")
    max_retries = 250
    completed = False
    for i in range(max_retries):
        r = httpx.get(f"{API_URL}/consultations/{cid}/progress", auth=AUTH)
        assert r.status_code == 200
        prog = r.json()
        print(f"  [Attempt {i+1}] status={prog.get('status')} | {prog.get('done')}/{prog.get('total')} completed ({prog.get('percent')}%)")
        
        if prog.get("status") == "done":
            completed = True
            break
        elif prog.get("status") == "error":
            raise RuntimeError(f"Job failed during generation: {details.get('error_message')}")
        
        time.sleep(2)

    assert completed, "TTS generation timed out"
    print("✓ Synthesis completed successfully!")

    # 5. Downloading ZIP and checking content structure
    print("\n5. Downloading generated audio ZIP file...")
    r = httpx.get(f"{API_URL}/consultations/{cid}/download", auth=AUTH)
    assert r.status_code == 200, f"ZIP download failed: {r.text}"
    
    zip_data = io.BytesIO(r.content)
    with zipfile.ZipFile(zip_data) as z:
        file_list = z.namelist()
        print(f"ZIP Files: {file_list}")
        
        # Verify transcript and WAV files exist
        has_transcript = any(f.endswith("transcript.txt") for f in file_list)
        has_info = any(f.endswith("info.json") for f in file_list)
        has_full = any(f.endswith("full_consultation.wav") for f in file_list)
        assert has_transcript
        assert has_info
        assert has_full
        
        # Verify each speaker turn has its individual WAV
        wav_files = [f for f in file_list if f.endswith(".wav") and not f.endswith("full_consultation.wav")]
        assert len(wav_files) == 2, f"Expected 2 turn WAV files, found {len(wav_files)}"
        print("✓ ZIP package contains all required transcripts and audio clips!")

    # 6. Testing direct WAV download
    print("\n6. Downloading direct WAV file with query parameter authentication...")
    # Test streaming (no download header)
    r_stream = httpx.get(f"{API_URL}/consultations/{cid}/audio/full?pwd=opdaudio2026")
    assert r_stream.status_code == 200, f"Full audio stream failed: {r_stream.text}"
    assert "attachment" not in r_stream.headers.get("content-disposition", "")
    assert r_stream.headers.get("content-type") == "audio/wav"
    
    # Test downloading (with download header & custom filename)
    r_download = httpx.get(f"{API_URL}/consultations/{cid}/audio/full?download=true&pwd=opdaudio2026")
    assert r_download.status_code == 200, f"Full audio download failed: {r_download.text}"
    content_disp = r_download.headers.get("content-disposition", "")
    assert "attachment" in content_disp, f"Expected attachment header, got: {content_disp}"
    assert "E2E_Test_Simple_Mode.wav" in content_disp, f"Expected custom filename in header, got: {content_disp}"
    assert r_download.headers.get("content-type") == "audio/wav"
    print("✓ Direct WAV download and query param authentication: SUCCESS!")

    print("\n==========================================")
    print("E2E Randomization Integration Test: SUCCESS!")
    print("==========================================")

if __name__ == "__main__":
    test_e2e_randomization()

