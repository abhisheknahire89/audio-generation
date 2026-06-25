# Indian OPD Consultation Audio Generator — Technical Setup Guide

This document describes how to configure, run, and host the OPD Audio Generator application on a macOS machine.

---

## Prerequisites

1. **Python 3.11** or similar.
2. **NodeJS & npm** (tested on Node v25).
3. **macOS `caffeinate` utility** (pre-installed by default on macOS).
4. **Hugging Face Account**: Needed for access to gated AI4Bharat TTS models.

---

## Hugging Face Gated Repository Access

The AI4Bharat models used in this project are gated on Hugging Face. To download and run them locally:

1. **Create an account** on [Hugging Face](https://huggingface.co).
2. **Accept model terms** on both repository pages:
   - [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts)
   - [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5)
3. **Generate a User Access Token**: Go to Hugging Face Settings -> Access Tokens, and create a `Read` token.
4. **Set Environment Variable**: When starting the application, provide the token:
   ```bash
   export HF_TOKEN="your_hugging_face_read_token"
   ```

---

## Installation & Setup

1. **Clone & Navigate**:
   Ensure you are in the application root directory:
   ```bash
   cd "/Users/abhishekpravinnahire/Desktop/Audio Generation/opd-audio-generator"
   ```

2. **Setup Python Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Configure Git for LFS Bypass** (Crucial if git-lfs is missing on system):
   Parler-TTS installer clones sub-packages via Git. Run these commands to prevent Git from stalling on LFS files:
   ```bash
   git config --global filter.lfs.required false
   git config --global filter.lfs.smudge cat
   git config --global filter.lfs.clean cat
   git config --global --unset filter.lfs.process
   ```

4. **Install Python Packages**:
   ```bash
   pip install -r requirements.txt
   pip install git+https://github.com/huggingface/parler-tts.git
   pip install indic-transliteration
   ```

5. **Generate Synthetic Reference Clips for IndicF5**:
   ```bash
   python generate_reference_clips.py
   ```

6. **Build React Frontend**:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

---

## Starting the Application

Use the one-command launcher. It activates the virtual environment and runs the FastAPI server under `caffeinate` to prevent your Mac from sleeping during long overnight generations:

```bash
export HF_TOKEN="your_hugging_face_read_token"
./start.sh
```

The application will be served at a single URL:
**[http://localhost:8000](http://localhost:8000)**

You can access the full React dashboard in your browser. All API calls, script uploads, background noise overlays, and ZIP compilation will run seamlessly.
