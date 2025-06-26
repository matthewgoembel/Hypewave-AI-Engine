import re
import base64
import subprocess
import os

# --- Text/Bias Parsing ---
def extract_bias_intent_timeframe(text: str) -> dict:
    bias_keywords = ["long", "short", "neutral"]
    timeframe_match = re.search(r"\b(\d+[mhHdD])\b", text.lower())
    bias = next((word for word in bias_keywords if word in text.lower()), "neutral")
    intent = text.strip()
    return {
        "bias": bias,
        "timeframe": timeframe_match.group(1) if timeframe_match else "1H",
        "intent": intent
    }

# --- Chart Screenshot Capture ---
def capture_chart(symbol: str, timeframe: str) -> str:
    """
    Calls the Puppeteer script to capture a chart screenshot.
    Returns the path to the saved PNG file, or None if it failed.
    """
    try:
        print(f"[📸] Capturing chart for {symbol} {timeframe}...")
        subprocess.run(["node", "hypewave-screenshot/screenshot.js", symbol, timeframe], check=True)
        path = f"media/{symbol}_{timeframe}.png"
        return path if os.path.exists(path) else None
    except Exception as e:
        print(f"[❌ Screenshot Error] {e}")
        return None

# --- Base64 Encode Chart ---
def encode_chart_to_base64(image_path: str) -> str:
    """
    Converts a PNG file to base64 for use in OpenAI Vision input.
    """
    with open(image_path, "rb") as img:
        return base64.b64encode(img.read()).decode("utf-8")
