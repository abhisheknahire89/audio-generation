# Indian OPD Consultation Audio Generator — User Guide

A local, easy-to-use application that turns written doctor–patient consultation scripts into realistic Indian outpatient department (OPD) audio dialogues.

---

## How to Start the App

1. Ask your technical team to complete the setup instructions in [SETUP.md](file:///Users/abhishekpravinnahire/Desktop/Audio%20Generation/opd-audio-generator/SETUP.md).
2. Open terminal in the project directory, set your Hugging Face token, and run:
   ```bash
   export HF_TOKEN="your_token_here"
   ./start.sh
   ```
3. Open your browser and navigate to:
   **[http://localhost:8000](http://localhost:8000)**

---

## Core Flow

### 1. Submit your script
You can generate audio in two ways:
*   **Write or Paste**: Type or paste your consultation script directly into the text editor.
*   **File Upload**: Drag and drop any script file (`.txt`, `.md`, `.pdf`, `.docx`, `.json`).

The script must separate turns by starting each line with the speaker name followed by a colon (e.g. `Doctor:` or `Patient:`).

### 2. Configure Speakers & Voices
The system automatically parses your script and detects all unique speakers. Under **Speaker Voice Mapping**:
*   Choose the **Gender** (Male/Female) and **Age Bracket** (Adult/Elderly/Young) for each speaker.
*   The default synthesis engine is **Indic-Parler-TTS** (recommended for faster synthesis and wide language support).
*   Add a **Voice Prompt** description in plain English to customize how the speaker sounds (e.g. *"A middle-aged doctor speaking very calmly, clear Hindi accent"*).

### 3. Add Ambient Hospital Noise
Make the audio sound like a real clinical environment.
*   Turn on **Clinic Ambient Noise**.
*   Select the types of background noise to layer (e.g. *Hospital Ambience, AC Hum, Keyboard Typing, Door Sounds, Nearby Chatter*).
*   Adjust the **Noise Intensity slider** to control the background volume.

### 4. Generate & Track Progress
*   Click **Generate Consultation Audio**.
*   The background job runner will queue the speech turns and process them one by one.
*   A **Progress Bar** will display the percentage completed, and a dynamic **Estimated Time Remaining** counter will show how much time is left.
*   You can safely refresh the browser or close the tab; the generation runs in the background and will resume where it left off.

### 5. Preview & Download
*   Go to the **History Library** tab to see completed consultations.
*   Play individual conversation turns to preview them.
*   Play the combined **Full OPD Consultation** track.
*   Click **Download ZIP** to get a single file containing all individual speech turns (in `.wav` format), the full mixed audio, the original text transcript, and metadata info.

---

## Batch Mode
If you have multiple consultation scripts to process:
1. Navigate to the **Batch Queue** tab.
2. Enter a Batch Name.
3. Click **Add another script** to configure multiple scripts.
4. Click **Queue Batch Generation** to run them sequentially.
5. Download individual script files or the full batch ZIP from the history list once complete.
