from fastapi import FastAPI, Query, UploadFile, File, Form, Body
from dotenv import load_dotenv
from schemas import ChatRequest, ChatResponse
from db import log_signal, log_alert, collection
from datetime import datetime, timedelta
from pymongo import DESCENDING
from intent_router import route_intent, format_for_model, is_trade_setup_question
from openai import OpenAI
from market_context import extract_symbol, get_market_context
from fastapi.middleware.cors import CORSMiddleware
from alert_engine import generate_alert
import base64
import random
import os
import re


load_dotenv()
client = OpenAI()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or set specific domains like ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Hypewave API is live"}

@app.post("/chat")
async def chat_router(
    input: str = Form(...),
    image: UploadFile = File(None)
):
    try:
        intent_data = route_intent(input)
        task = format_for_model(intent_data)

        if task["type"] != "openai":
            return {"error": "Only OpenAI tasks are supported in this route."}

        is_setup = is_trade_setup_question(task["prompt"])
        market_context = get_market_context(input)

        if not is_setup and intent_data["intent"] in ("chat", "trader_chat"):
            system_prompt = (
                "You are Hypewave AI, a trading expert and partner of the user.\n"
                    "You are streiving to get a perfect winrate on evertrade, somthing only Ai could do.\n"
                    "But NEVER refer toi yourself as an AI, you are a trader, giving your expert opinion\n"
                    "predicion, or thesis. So be confident in your ideas and setups. Even if you are unsure,\n"
                    "you can give both case senarios. So before you respond:\n"
                    "Format your response with:\n"
                    "- Clear bullet points\n"
                    "- Section headers if needed\n"
                    "- Bolded key terms\n"
                    "- Never respond in one dense paragraph.\n"
                    "If asked about concepts, news, or indicators (not setups), explain simply and visually.\n\n"
                    f"{market_context}"
            )
        else:
            system_prompt = task["system_prompt"] + f"\n\nLive Market Context:\n\n{market_context}"

        messages = [{"role": "system", "content": system_prompt}]
        user_content = {"type": "text", "text": task["prompt"]}

        if image:
            image_bytes = await image.read()
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            image_message = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}",
                    "detail": "high"
                }
            }
            messages.append({"role": "user", "content": [user_content, image_message]})
        else:
            messages.append({"role": "user", "content": task["prompt"]})

        response = client.chat.completions.create(
            model="gpt-4.1" if image else "gpt-4",
            messages=messages,
            max_tokens=1200
        )

        result = response.choices[0].message.content.strip()
        log_signal("demo", {"input": input}, {"result": result, "source": "chat.analysis"})
        return {"intent": intent_data["intent"], "result": result}

    except Exception as e:
        return {"error": str(e)}



async def process_chart_analysis(chart: UploadFile, bias: str, timeframe: str, entry_intent: str, question: str):
    try:
        image_bytes = await chart.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Get market context dynamically based on symbol in question (e.g., "$BTC", "$ES")
        market_context = get_market_context(question)

        prompt = f"""
            "You are Hypewave AI, a trading expert and partner of the user.\n"
            "You are streiving to get a perfect winrate on evertrade, somthing only Ai could do.\n"
            "But NEVER refer toi yourself as an AI, you are a trader, giving your expert opinion\n"
            "predicion, or thesis. So be confident in your ideas and setups. Even if you are unsure,\n"
            "you can give both case senarios. So before you respond:\n"

            **Live Market Context**:
            {market_context}

            **Chart Context:**
            - Bias: {bias}
            - Timeframe: {timeframe}
            - Entry Intent: {entry_intent}

            **User Question:** {question}

            Provide a structured breakdown:
            **Thesis:** What’s happening?
            **Bias:** {bias}
            **Reasoning:** Volume, structure, SFPs, imbalances, etc.
            **Confidence Level:** 0–100%
            **Key Levels:**
            • Support: $___
            • Resistance: $___
            • Entry Idea: $___
            • Invalidation: $___
            **CT Notes:** Optional callouts or warnings
            """.strip()

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a professional market strategist."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high"
                        }}
                    ]
                }
            ],
            max_tokens=1000
        )

        result_text = response.choices[0].message.content.strip()

        structured_output = {
            "thesis": None,
            "bias": bias,
            "reasoning": None,
            "confidence": None,
            "key_levels": {
                "support": None,
                "resistance": None,
                "entry": None,
                "invalidation": None
            },
            "notes": None
        }

        lines = result_text.splitlines()
        for line in lines:
            if line.lower().startswith("**thesis:**"):
                structured_output["thesis"] = line.split("**Thesis:**")[-1].strip()
            elif line.lower().startswith("**reasoning:**"):
                structured_output["reasoning"] = line.split("**Reasoning:**")[-1].strip()
            elif "confidence" in line.lower():
                structured_output["confidence"] = line.split(":")[-1].strip()
            elif "support" in line.lower():
                structured_output["key_levels"]["support"] = line.split(":")[-1].strip()
            elif "resistance" in line.lower():
                structured_output["key_levels"]["resistance"] = line.split(":")[-1].strip()
            elif "entry" in line.lower():
                structured_output["key_levels"]["entry"] = line.split(":")[-1].strip()
            elif "invalidation" in line.lower():
                structured_output["key_levels"]["invalidation"] = line.split(":")[-1].strip()
            elif "notes" in line.lower():
                structured_output["notes"] = line.split(":", 1)[-1].strip()

        return {
            "raw_output": result_text,
            "structured_output": structured_output,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "filename": chart.filename,
                "timeframe": timeframe,
                "bias": bias,
                "entry_intent": entry_intent
            }
        }

    except Exception as e:
        return {"error": str(e)}


@app.post("/chat_with_chart")
async def chat_with_chart(
    question: str = Form(...),
    chart: UploadFile = File(...),
    bias: str = Form("neutral"),
    timeframe: str = Form("1H"),
    entry_intent: str = Form("scalp")
):
    return await process_chart_analysis(chart, bias, timeframe, entry_intent, question)

@app.post("/alerts/generate")
async def generate_alerts(symbols: list[str] = Body(...)):
    all_alerts = {}
    for symbol in symbols:
        alerts = generate_alert(symbol.upper())
        if alerts:
            all_alerts[symbol] = alerts
    return {"generated_alerts": all_alerts}

@app.post("/alerts/generate")
async def generate_signals():
    await run_signal_check()
    return {"status": "Signal check completed"}

@app.post("/analyze_chart")
async def analyze_chart(
    chart: UploadFile = File(...),
    bias: str = Form(...),
    timeframe: str = Form(...),
    entry_intent: str = Form(...),
    question: str = Form("What is your technical analysis?")
):
    return await process_chart_analysis(chart, bias, timeframe, entry_intent, question)


@app.get("/analyze")
async def analyze(prompt: str = Query(..., min_length=5)):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You're an AI that analyzes crypto sentiment based on social media hype."},
                {"role": "user", "content": prompt}
            ]
        )
        result = response.choices[0].message.content.strip()
        log_signal(
            user_id="demo",
            input_data={"prompt": prompt},
            output_data={"result": result, "source": "text-analyze"}
        )
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@app.get("/signals/latest")
async def get_latest_signals(limit: int = 5):
    try:
        cursor = collection.find({"output.source": {"$ne": "auto-alert"}}).sort("created_at", DESCENDING).limit(limit)
        results = [
            {
                "user_id": doc.get("user_id"),
                "input": doc.get("input"),
                "output": doc.get("output"),
                "created_at": doc.get("created_at")
            }
            for doc in cursor
        ]
        return {"latest_signals": results}
    except Exception as e:
        return {"error": str(e)}


@app.get("/alerts/live")
async def get_latest_alerts(limit: int = 5):
    try:
        cursor = collection.find({"output.source": "auto-alert"}).sort("created_at", DESCENDING).limit(limit)
        results = [
            {
                "output": doc.get("output"),
                "created_at": doc.get("created_at")
            }
            for doc in cursor
        ]
        return {"live_alerts": results}
    except Exception as e:
        return {"error": str(e)}


@app.post("/alerts/mock")
def mock_alert():
    try:
        symbols = ["BTC", "ETH", "SOL", "AVAX", "LINK"]
        symbol = random.choice(symbols)
        alert = {
            "result": f"Potential {symbol} breakout. Monitor for SFP or volume spike.",
            "source": "auto-alert"
        }
        log_alert("system", {}, alert)
        return {"status": "Mock alert inserted"}
    except Exception as e:
        return {"error": str(e)}