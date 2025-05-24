from fastapi import FastAPI, Query, UploadFile, File, Form
from dotenv import load_dotenv
import os
import openai

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hypewave API is live"}

@app.get("/analyze")
async def analyze(prompt: str = Query(..., min_length=5)):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You're an AI that analyzes crypto sentiment based on social media hype."},
                {"role": "user", "content": prompt}
            ]
        )
        result = response.choices[0].message.content.strip()
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

@app.post("/analyze_chart")
async def analyze_chart(
    chart: UploadFile = File(...),
    bias: str = Form(...),
    timeframe: str = Form(...),
    entry_intent: str = Form("entry setup")
):
    # This is a MOCK — Vision not enabled yet.
    prompt = f"""
    You are Hypewave AI, a professional crypto market analyst.

    Analyze a chart image submitted by a trader with this context:
    - Bias: {bias}
    - Timeframe: {timeframe}
    - Entry Intent: {entry_intent}

    Return the result in this format:
    ---
    🧠 Hypewave Signal:
    Setup: [Pattern]
    Bias: {bias}
    Volume: [Low/Med/High]
    Confidence: 0–100%

    Entry Zone: [Price]
    Invalidation: [Stop level]
    Notes: [Short CT-style comment]
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",  # Replace with vision model when available
            messages=[
                {"role": "system", "content": "You are a crypto chart analyst."},
                {"role": "user", "content": prompt}
            ]
        )
        result = response.choices[0].message.content.strip()
        return {
            "result": result,
            "note": "Chart image not processed yet (mocked until vision model enabled)"
        }
    except Exception as e:
        return {"error": str(e)}
