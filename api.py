from fastapi import FastAPI, Query, UploadFile, File, Form, Body, Request, BackgroundTasks, Depends
from dotenv import load_dotenv
from schemas import ChatRequest, ChatResponse
from db import log_signal, collection, log_chat, chats_coll
from datetime import datetime, timedelta, timezone
from pymongo import DESCENDING
from openai import OpenAI
from market_context import extract_symbol, get_market_context
from fastapi.middleware.cors import CORSMiddleware
from db import get_latest_news
from signal_engine import generate_alerts_for_symbol
from market_data_ws import get_latest_ohlc, start_ws_listener
from fastapi.staticfiles import StaticFiles
import asyncio
import base64, random, os, re, threading
from bson import ObjectId
from economic_scraper import scrape_marketwatch_calendar
from contextlib import asynccontextmanager
from auth_routes import router as auth_router
from auth_utils import decode_access_token
from auth_routes import get_current_user
from pathlib import Path
from winrate_checker import get_winrate  # ✅ Added for winrate route


load_dotenv()
client = OpenAI()


@asynccontextmanager
async def lifespan(app):
    start_ws_listener() # Start signal engine
    yield

# Create FastAPI app *before* using it
app = FastAPI(lifespan=lifespan)

# Include routers, middlewares, and mounts
# app.include_router(forex_router)

# Include login system
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# local image mount direcotry and relize
#app.mount("/media", StaticFiles(directory="/mnt/data"), name="media")

media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)

app.mount("/media", StaticFiles(directory=str(media_path)), name="media")

@app.head("/")
def root_head(request: Request):
    return {"ok": True}


@app.get("/")
def root():
    return {"message": "Hypewave AI is live 🚀"}

# chat pannel backend - GPT + Binance websocksets
@app.post("/chat")
async def chat_router(
    request: Request,
    input: str = Form(...),
    image: UploadFile = File(None),
    bias: str = Form("neutral"),
    timeframe: str = Form("1H"),
    entry_intent: str = Form("scalp")
):
    try:
        # Determine if the user is authenticated
        token_header = request.headers.get("authorization")
        user_id = "guest"
        if token_header:
            token = token_header.replace("Bearer ", "")
            payload = decode_access_token(token)
            if payload:
                user_id = payload.get("sub", "guest")

        # Extract the symbol
        KNOWN_SYMBOLS = ["BTC", "ETH", "SOL", "XAU", "SPX", "NASDAQ"]

        def extract_symbol(text: str):
            text = text.upper()
            for sym in KNOWN_SYMBOLS:
                if f"${sym}" in text or sym in text:
                    return sym
            return "BTC"

        symbol = extract_symbol(input)

        # Live OHLC
        ohlc_list = get_latest_ohlc(f"{symbol}USDT", "1h") or []
        price_data = ohlc_list[-1] if isinstance(ohlc_list, list) and ohlc_list else {}

        price_summary = (
            f"**Live Price Data for ${symbol}:**\n"
            f"- Price: ${price_data.get('close', 'N/A')}\n"
            f"- Open: {price_data.get('open', 'N/A')} | High: {price_data.get('high', 'N/A')} | Low: {price_data.get('low', 'N/A')}\n"
            f"- Volume: {price_data.get('volume', 'N/A')}\n"
        )

        market_context = get_market_context(symbol)

        system_prompt = f"""
You are Hypewave AI, your friendly trading assistant.

Goals:
- Answer any trading or market-related question confidently.
- Reference live market data.
- Offer clear and actionable insights.
- Format responses in markdown with clear sections.

**Live Data Summary:**
{price_summary}

**Market Context:**
{market_context}
"""

        messages = [{"role": "system", "content": system_prompt}]
        user_content = {"type": "text", "text": input}

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
            messages.append({"role": "user", "content": input})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500
        )

        raw_output = response.choices[0].message.content.strip()

        log_chat(user_id, {"input": input}, {"result": raw_output, "source": "chat.analysis"})

        return {"result": raw_output}

    except Exception as e:
        return {"result": f"⚠️ Error: {str(e)}"}
    

    
@app.get("/chat/history")
def get_chat_history(user=Depends(get_current_user)):
    user_id = user["user_id"]

    messages = list(
        chats_coll
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(20)
    )
    messages.reverse()

    return [
        {
            "role": "user",
            "text": m.get("input", {}).get("input", ""),
            "timestamp": m.get("created_at").isoformat() if m.get("created_at") else None
        }
        if m.get("input")
        else {
            "role": "ai",
            "text": m.get("output", {}).get("result", ""),
            "timestamp": m.get("created_at").isoformat() if m.get("created_at") else None
        }
        for m in messages
    ]


"""
@app.post("/chat_with_chart")
async def chat_with_chart(
    question: str = Form(...),
    chart: UploadFile = File(...),
    bias: str = Form("neutral"),
    timeframe: str = Form("1H"),
    entry_intent: str = Form("scalp")
):
    return await process_chart_analysis(chart, bias, timeframe, entry_intent, question)
"""

@app.post("/signals/manual-scan")
async def generate_alerts(symbols: list[str] = Body(...)):
    all_alerts = {}
    for symbol in symbols:
        alerts = generate_alerts_for_symbol(symbol.upper())
        if alerts:
            all_alerts[symbol] = alerts
    return {"generated_alerts": all_alerts}


@app.get("/economic-calendar")
def get_economic_calendar():
    try:
        data = scrape_marketwatch_calendar()
        return {"calendar": data}
    except Exception as e:
        return {"error": str(e)}


@app.get("/news/latest")
async def fetch_news(limit: int = 20):
    try:
        return get_latest_news(limit=limit)
    except Exception as e:
        return {"error": str(e)}



@app.get("/signals/latest")
async def get_latest_signals(
    skip: int = Query(0, ge=0),
    limit: int = Query(24, le=50),  # ⬅️ Default is now 24
    min_confidence: int = Query(60, ge=0, le=100)
):
    from db import client as mongo_client
    signals_coll = mongo_client["hypewave"]["signals"]

    # Fetch recent signals sorted by most recent
    cursor = signals_coll.find(
        {
            "output.source": "AI Multi-Timeframe Engine",
            "output.confidence": {"$gte": min_confidence}
        }
    ).sort("created_at", -1).skip(skip).limit(limit)

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

from winrate_checker import get_winrate

@app.get("/signals/winrate")
def get_global_winrate():
    return get_winrate()
