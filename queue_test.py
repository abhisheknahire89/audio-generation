import requests
import time
import json

API_URL = "http://localhost:8000/api"

def queue_jobs():
    for i in range(1, 6):
        data = {
            "name": f"Test Script {i}",
            "script": "Doctor: Hello.\nPatient: Hi.\nDoctor: How are you?\nPatient: I am fine.",
            "language": "hi_en",
            "engine": "parler",
            "seed": 42,
            "speaker_settings": {},
            "noise_settings": {
                "enabled": False,
                "types": {},
                "intensity": 0.0
            },
            "randomize": False
        }
        res = requests.post(f"{API_URL}/consultations", data={"request_json": json.dumps(data)})
        if res.status_code == 200:
            print(f"Queued Test Script {i}: {res.json()['id']}")
        else:
            print(f"Failed to queue Test Script {i}: {res.text}")
        time.sleep(0.5)

if __name__ == "__main__":
    queue_jobs()
