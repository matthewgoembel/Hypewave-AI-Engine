#!/bin/bash
echo "Starting Hypewave AI backend..."
uvicorn api:app --host 0.0.0.0 --port 10000