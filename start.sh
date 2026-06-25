#!/bin/bash
# One-command launcher for Indian OPD Audio Generator
# Runs under 'caffeinate' to keep the Mac awake during overnight batches.

set -e

# Get script folder path
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=========================================================="
echo " Starting Indian OPD Consultation Audio Generator"
echo "=========================================================="

# Activate Python virtual environment
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Error: .venv virtual environment not found. Please run setup first."
    exit 1
fi

# Load environment variables from .env if present
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Serve the app and API on a single port (8000) using uvicorn under caffeinate
echo "Starting uvicorn server under 'caffeinate' to prevent sleeping..."
echo "Web interface: http://localhost:8000"
echo "=========================================================="
echo "Press Ctrl+C to stop the server."
echo ""

# caffeinate options:
# -i : prevent system idle sleep
# -m : prevent disk idle sleep
# -s : prevent system sleep when on AC power
caffeinate -ims python backend/main.py
