# Keeping It Running — Technical Operator's Guide

This guide describes how to run, monitor, and restart both the audio generation server and the Cloudflare Tunnel.

---

## 1. Startup & Sleep Prevention

The server launcher automatically runs under macOS `caffeinate` to prevent the host Mac from going to sleep during background speech generation:

1.  Open Terminal on the host Mac.
2.  Navigate to the project root:
    ```bash
    cd "/Users/abhishekpravinnahire/Desktop/Audio Generation/opd-audio-generator"
    ```
3.  Execute the one-command launcher:
    ```bash
    ./start.sh
    ```
This loads variables from `.env`, starts uvicorn binding on `0.0.0.0:8000`, and runs background audio mixing.

---

## 2. Cloudflare Tunnel Management

We have downloaded the official `cloudflared` binary into the project root. To establish the public connection:

1.  Open a new Terminal window.
2.  Navigate to the project root:
    ```bash
    cd "/Users/abhishekpravinnahire/Desktop/Audio Generation/opd-audio-generator"
    ```
3.  Start the tunnel pointing at local port `8000`:
    ```bash
    ./cloudflared tunnel --url http://localhost:8000
    ```
4.  Copy the generated URL (it will look like `https://*.trycloudflare.com`) and share it with your associate.

---

## 3. Hugging Face Gated Repo Authorization

If background speech generation throws a `GatedRepoError` or a `403 Forbidden` status during Parler-TTS or IndicF5 loading:

1.  Visit the model repositories on Hugging Face:
    *   [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts)
    *   [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5)
2.  Log in using the Hugging Face account associated with the token defined in the `.env` file (`HF_TOKEN`).
3.  Click the button to **Accept Terms and Request Access** (access is granted instantly under Apache 2.0).
4.  Once authorized on Hugging Face, restart the uvicorn server (Ctrl+C, then `./start.sh`), and generation requests will process successfully.

---

## 4. Resetting and Restarting

If the port is busy or processes are hung:

### Freeing Port 8000
Check for any existing python or uvicorn instances listening on port 8000:
```bash
lsof -i :8000
```
Kill the stale processes:
```bash
kill -9 <PID>
```

### Changing Settings
To modify the security password or host bindings, edit the `.env` file:
```env
HOST=0.0.0.0
PORT=8000
HF_TOKEN=hf_...
```
Restart the application to apply modifications.
