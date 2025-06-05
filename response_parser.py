import re

def parse_gpt_response(text: str) -> dict:
    keys = ["Bias", "Volume", "Confidence", "Trade Setup", "Notes"]
    result = {}
    for key in keys:
        match = re.search(f"{key}: (.+)", text, re.IGNORECASE)
        result[key.lower().replace(' ', '_')] = match.group(1).strip() if match else "N/A"
    return result