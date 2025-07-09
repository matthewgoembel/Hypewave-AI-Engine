from fastapi import FastAPI, Query, UploadFile, File, Form, Body, Request, BackgroundTasks
from dotenv import load_dotenv
from schemas import ChatRequest, ChatResponse
from db import log_signal, collection, log_chat
from datetime import datetime, timedelta, timezone
from pymongo import DESCENDING
from intent_router import route_intent, format_for_model, is_trade_setup_question
from openai import OpenAI
from market_context import extract_symbol, get_market_context
from fastapi.middleware.cors import CORSMiddleware
from db import get_latest_news
from signal_engine import generate_alerts_for_symbol
from market_data_ws import start_ws_listener
from fastapi.staticfiles import StaticFiles
import asyncio
import base64, random, os, re, threading
from bson import ObjectId
from forex_calender import router as forex_router
from contextlib import asynccontextmanager

load_dotenv()
client = OpenAI()


@asynccontextmanager
async def lifespan(app):
    # 🟢 No more Telegram fetch task here.
    # 🔹 Start your other startup tasks if needed:
    start_ws_listener()

    yield

    # 🔹 Clean shutdown of any other resources (if you have them)


# ✅ Create FastAPI app *before* using it
app = FastAPI(lifespan=lifespan)

# ✅ Include routers, middlewares, and mounts
app.include_router(forex_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media", StaticFiles(directory="/mnt/data"), name="media")

@app.head("/")
def root_head(request: Request):
    return {"ok": True}


@app.get("/")
def root():
    return {"message": "Hypewave AI is live 🚀"}

@app.post("/chat")
async def chat_router(
    input: str = Form(...),
    image: UploadFile = File(None)
):
    try:
        import re

        KNOWN_SYMBOLS = ["BTC", "ETH", "SOL", "XAU", "SPX", "NASDAQ"]

        def extract_symbol(text: str):
            text = text.upper()
            for sym in KNOWN_SYMBOLS:
                if f"${sym}" in text or sym in text:
                    return sym
            return "BTC"

        intent_data = route_intent(input)
        task = format_for_model(intent_data)

        if task["type"] != "openai":
            return {"error": "Only OpenAI tasks are supported in this route."}

        symbol = extract_symbol(input)

        # 1️⃣ Live OHLC
        from market_data_ws import get_latest_ohlc
        ohlc_list = get_latest_ohlc(f"{symbol}USDT", "1h") or []
        price_data = ohlc_list[-1] if isinstance(ohlc_list, list) and ohlc_list else {}

        price_summary = (
            f"<b>Live Price Data for ${symbol}:</b><br>"
            f"• Price: ${price_data.get('close', 'N/A')}<br>"
            f"• Open: {price_data.get('open', 'N/A')} | High: {price_data.get('high', 'N/A')} | Low: {price_data.get('low', 'N/A')}<br>"
            f"• Volume: {price_data.get('volume', 'N/A')}<br>"
        )

        # 2️⃣ Macro/sentiment context
        market_context = get_market_context(input)

        # 3️⃣ Build prompt
        system_prompt = (
            f"{task['system_prompt']}\n\n"
            f"{price_summary}\n"
            f"<b>Market Context:</b><br>{market_context}\n\n"
            f"🧠 Use bold headers, bullet points, and no dense paragraphs."
        )

        # 4️⃣ Build GPT request
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
            model="gpt-4o",
            messages=messages,
            max_tokens=1200
        )

        raw_output = response.choices[0].message.content.strip()

        log_chat("demo", {"input": input}, {"result": raw_output, "source": "chat.analysis"})

        return {"intent": intent_data["intent"], "result": raw_output}

    except Exception as e:
        return {
            "intent": "error",
            "result": f"<b>⚠️ Error:</b><br>{str(e)}"
        }


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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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

@app.post("/signals/manual-scan")
async def generate_alerts(symbols: list[str] = Body(...)):
    all_alerts = {}
    for symbol in symbols:
        alerts = generate_alerts_for_symbol(symbol.upper())
        if alerts:
            all_alerts[symbol] = alerts
    return {"generated_alerts": all_alerts}

@app.post("/analyze_chart")
async def analyze_chart(
    chart: UploadFile = File(...),
    bias: str = Form(...),
    timeframe: str = Form(...),
    entry_intent: str = Form(...),
    question: str = Form("What is your technical analysis?")
):
    return await process_chart_analysis(chart, bias, timeframe, entry_intent, question)

@app.get("/news/latest")
async def fetch_news(limit: int = 10):
    try:
        return get_latest_news(limit=limit)
    except Exception as e:
        return {"error": str(e)}



@app.get("/signals/latest")
async def get_latest_signals(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=50),
    min_confidence: int = Query(60, ge=0, le=100)
):
    from db import client as mongo_client
    signals_coll = mongo_client["hypewave"]["signals"]

    # Define cutoff as 24 hours ago
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    base_query = {
        "output.source": "AI Candle Engine",
        "output.confidence": {"$gte": min_confidence},
        "created_at": {"$gte": cutoff}
    }

    cursor = signals_coll.find(base_query).sort("created_at", DESCENDING).skip(skip).limit(limit)
    results = list(cursor)

    response = [
        {
            "signal_id": str(doc.get("_id")),
            "user_id": doc.get("user_id"),
            "input": doc.get("input"),
            "output": doc.get("output"),
            "created_at": doc.get("created_at")
        }
        for doc in results
    ]

    return {"latest_signals": response}


@app.get("/alerts/live")
async def get_latest_alerts(limit: int = 5):
    from db import client as mongo_client
    alerts_coll = mongo_client["hypewave"]["alerts"]

    try:
        cursor = alerts_coll.find().sort("created_at", -1).limit(limit)
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

@app.post("/signals/feedback")
async def record_signal_feedback(
    signal_id: str = Body(...),
    feedback: str = Body(...)
):
    try:
        from db import client as mongo_client
        signals_coll = mongo_client["hypewave"]["signals"]

        if feedback not in ["up", "down"]:
            return {"error": "Invalid feedback"}

        from db import log_feedback
        log_feedback(signal_id, feedback)
        return {"status": "feedback recorded"}

    except Exception as e:
        return {"error": str(e)}