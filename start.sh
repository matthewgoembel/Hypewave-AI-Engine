#!/usr/bin/env bash

echo "📁 Installing Node dependencies..."
cd hypewave-screenshot
npm install

cd ..

echo "🚀 Starting Hypewave AI backend..."
uvicorn api:app --host 0.0.0.0 --port 10000
