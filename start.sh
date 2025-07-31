#!/usr/bin/env bash

echo "🚀 Starting Hypewave AI backend..."

# Start FastAPI in the background
uvicorn api:app --host 0.0.0.0 --port 10000 &

# Start Telegram live feed in the foreground
# python telegram_tracker.py
