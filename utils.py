import re

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
