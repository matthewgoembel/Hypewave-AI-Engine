from fastapi import FastAPI, Query, UploadFile, File, Form, Body, Request, BackgroundTasks
from dotenv import load_dotenv
from schemas import ChatRequest, ChatResponse
from db import log_signal, collection, log_chat
from datetime import datetime, timedelta, timezone
from pymongo import DESCENDING
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
    start_ws_listener()

    yield

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

# chat pannel backend - GPT + Binance websocksets
@app.post("/chat")
async def chat_router(
    input: str = Form(None),
    image: UploadFile = File(None),
    bias: str = Form("neutral"),
    timeframe: str = Form("1H"),
    entry_intent: str = Form("scalp")
):
    try:
        KNOWN_SYMBOLS = ["BTC", "ETH", "SOL", "XAU", "SPX", "NASDAQ"]

        def extract_symbol(text: str | None):
            if text:
                text = text.upper()
                for sym in KNOWN_SYMBOLS:
                    if f"${sym}" in text or sym in text:
                        return sym
            return "BTC"

        def is_trade_question(text: str | None):
            if not text:
                return False
            lowered = text.lower()
            keywords = ["long", "short", "entry", "setup", "signal", "buy", "sell", "scalp", "retest"]
            return any(k in lowered for k in keywords)

        symbol = extract_symbol(input)

        # Live OHLC
        from market_data_ws import get_latest_ohlc
        ohlc_list = get_latest_ohlc(f"{symbol}USDT", "1h") or []
        price_data = ohlc_list[-1] if isinstance(ohlc_list, list) and ohlc_list else {}

        price_summary = (
            f"**Live Price Data for ${symbol}:**\n"
            f"- Price: ${price_data.get('close', 'N/A')}\n"
            f"- Open: {price_data.get('open', 'N/A')} | High: {price_data.get('high', 'N/A')} | Low: {price_data.get('low', 'N/A')}\n"
            f"- Volume: {price_data.get('volume', 'N/A')}\n"
        )

        market_context = get_market_context(symbol)

        # Determine prompt style
        if is_trade_question(input):
            system_prompt = f"""
            You are Hypewave AI, a professional crypto trader.

            Goals:
            - Provide a decisive trade plan when asked about setups.
            - Always give clear entries, stops, and targets.
            - Avoid hedging or generic considerations.
            - Speak confidently.

            When asked for a setup, respond in this format:

            **Trade Idea:**
            Long or Short?

            **Entry Price:**
            Specific price or zone.

            **Stop Loss:**
            Exact invalidation level.

            **Target:**
            At least one profit target.

            **Reasoning:**
            Why you like this idea.

            **Confidence:**
            0–100%.

            **Risk Management:**
            Sizing and warnings.

            **Live Data:**
            {price_summary}

            **Market Context:**
            {market_context}
            """
        else:
            system_prompt = f"""
            You are Hypewave AI, a friendly trading assistant.

            Goals:
            - Answer any question accurately and confidently.
            - Reference live market data if relevant.
            - If the question is not about trading setups, provide clear and factual information.

            **Live Data:**
            {price_summary}

            **Market Context:**
            {market_context}
            """

        messages = [{"role": "system", "content": system_prompt}]

        # User content fallback
        if input:
            user_content = {"type": "text", "text": input}
        else:
            user_content = {"type": "text", "text": "Please analyze this chart and provide your best trading thesis."}

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
            messages.append({"role": "user", "content": user_content["text"]})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500
        )

        raw_output = response.choices[0].message.content.strip()

        log_chat("demo", {"input": input}, {"result": raw_output, "source": "chat.analysis"})

        return {"result": raw_output}

    except Exception as e:
        return {"result": f"⚠️ Error: {str(e)}"}



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