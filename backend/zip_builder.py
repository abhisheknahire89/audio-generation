"""
ZIP builder for consultation downloads.
"""
import io
import json
import zipfile
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime


def build_consultation_zip(
    consultation: Dict,
    utterances: List[Dict],
    output_dir: Path,
) -> bytes:
    """
    Build a ZIP in memory containing:
    - audio files (one per utterance, named NNN_Speaker.mp3)
    - full_consultation.mp3 (if exists)
    - transcript.txt
    - info.json
    """
    buf = io.BytesIO()
    cname = consultation.get("name", "consultation").replace(" ", "_")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add utterance audio files
        for utt in utterances:
            if utt.get("audio_path") and Path(utt["audio_path"]).exists():
                audio_path = Path(utt["audio_path"])
                idx = utt.get("sort_order", 0)
                speaker = utt.get("speaker", "Unknown").replace(" ", "_")
                arcname = f"{cname}/{idx:03d}_{speaker}{audio_path.suffix}"
                zf.write(str(audio_path), arcname)

        # Add full consultation audio if it exists
        full_audio = output_dir / "full_consultation.mp3"
        if full_audio.exists():
            zf.write(str(full_audio), f"{cname}/full_consultation.mp3")

        # Add transcript
        transcript_path = output_dir / "transcript.txt"
        if transcript_path.exists():
            zf.write(str(transcript_path), f"{cname}/transcript.txt")
        else:
            # Generate transcript from utterances
            lines = []
            for utt in utterances:
                lines.append(f"{utt.get('speaker', 'Unknown')}: {utt.get('text', '')}")
            zf.writestr(f"{cname}/transcript.txt", "\n".join(lines))

        # Add info.json
        info_path = output_dir / "info.json"
        if info_path.exists():
            zf.write(str(info_path), f"{cname}/info.json")
        else:
            info = build_info_json(consultation, utterances)
            zf.writestr(f"{cname}/info.json", json.dumps(info, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf.read()


def build_all_zip(
    consultations_data: List[Dict],  # list of (consultation, utterances, output_dir)
) -> bytes:
    """Build a ZIP containing all consultations."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in consultations_data:
            consultation = item["consultation"]
            utterances = item["utterances"]
            output_dir = Path(item["output_dir"])

            cname = consultation.get("name", "consultation").replace(" ", "_")
            cid_short = consultation.get("id", "")[:8]
            prefix = f"{cname}_{cid_short}"

            for utt in utterances:
                if utt.get("audio_path") and Path(utt["audio_path"]).exists():
                    audio_path = Path(utt["audio_path"])
                    idx = utt.get("sort_order", 0)
                    speaker = utt.get("speaker", "Unknown").replace(" ", "_")
                    arcname = f"{prefix}/{idx:03d}_{speaker}{audio_path.suffix}"
                    zf.write(str(audio_path), arcname)

            full_audio = output_dir / "full_consultation.mp3"
            if full_audio.exists():
                zf.write(str(full_audio), f"{prefix}/full_consultation.mp3")

            transcript_path = output_dir / "transcript.txt"
            if transcript_path.exists():
                zf.write(str(transcript_path), f"{prefix}/transcript.txt")
            else:
                lines = [f"{u.get('speaker','Unknown')}: {u.get('text','')}" for u in utterances]
                zf.writestr(f"{prefix}/transcript.txt", "\n".join(lines))

            info = build_info_json(consultation, utterances)
            zf.writestr(f"{prefix}/info.json", json.dumps(info, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf.read()


def build_info_json(consultation: Dict, utterances: List[Dict]) -> Dict:
    total_duration = sum(u.get("duration_seconds") or 0 for u in utterances)
    speakers = list({u.get("speaker", "Unknown") for u in utterances})
    return {
        "id": consultation.get("id"),
        "name": consultation.get("name"),
        "language": consultation.get("language"),
        "engine": consultation.get("engine"),
        "seed": consultation.get("seed"),
        "noise_settings": consultation.get("noise_settings", {}),
        "speakers": speakers,
        "total_utterances": len(utterances),
        "total_duration_seconds": round(total_duration, 2),
        "created_at": consultation.get("created_at"),
        "exported_at": datetime.utcnow().isoformat(),
    }


def save_consultation_files(
    output_dir: Path,
    consultation: Dict,
    utterances: List[Dict],
):
    """Save transcript.txt and info.json alongside audio files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # transcript.txt
    lines = []
    for utt in utterances:
        lines.append(f"{utt.get('speaker', 'Unknown')}: {utt.get('text', '')}")
    (output_dir / "transcript.txt").write_text("\n".join(lines), encoding="utf-8")

    # info.json
    info = build_info_json(consultation, utterances)
    (output_dir / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
