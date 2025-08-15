from fastapi import FastAPI, Query, UploadFile, File, Form, Body, Request, BackgroundTasks, Depends
from dotenv import load_dotenv
from schemas import ChatRequest, ChatResponse
from db import log_signal, collection, log_chat, chats_coll, votes_coll  
from datetime import datetime, timedelta, timezone
from pymongo import DESCENDING
from openai import OpenAI
from market_context import extract_symbol, get_market_context
from fastapi.middleware.cors import CORSMiddleware
from db import get_latest_news, set_user_push_token
from signal_engine import generate_alerts_for_symbol
from market_data_ws import get_latest_ohlc, start_ws_listener
from fastapi.staticfiles import StaticFiles
import asyncio
import base64, random, os, re, threading
import cloudinary # type: ignore
from bson import ObjectId
from economic_scraper import scrape_marketwatch_calendar
from contextlib import asynccontextmanager
from auth_routes import router as auth_router
from auth_utils import decode_access_token
from auth_routes import get_current_user
from pathlib import Path
from winrate_checker import get_winrate 
from cleanup_signals import close_signals_once
from pydantic import BaseModel

load_dotenv()


client = OpenAI()

cloudinary.config(
  cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
  api_key=os.getenv("CLOUDINARY_API_KEY"),
  api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

@asynccontextmanager
async def lifespan(app):
    # ✅ Ensure indexes & default fields once at startup
    try:
        # Unique vote per (signal_id, user_id)
        votes_coll.create_index([("signal_id", 1), ("user_id", 1)], unique=True)

        # Seed default feedback counters and normalize status
        from db import client as _mc
        _mc["hypewave"]["signals"].update_many(
            {"feedback": {"$exists": False}},
            {"$set": {"feedback": {"up": 0, "down": 0}}}
        )
        _mc["hypewave"]["signals"].update_many({"status": "OPEN"}, {"$set": {"status": "open"}})
    except Exception as _e:
        print("[startup] index/defaults error:", _e)

    # ✅ Start WS listener + AI engine
    start_ws_listener()

    # ✅ Start background closer loop (checks TP/SL hits)
    async def _closer_loop():
        while True:
            try:
                close_signals_once()
            except Exception as e:
                print("[closer] error:", e)
            await asyncio.sleep(60)
    asyncio.get_event_loop().create_task(_closer_loop())

    yield

class PushTokenBody(BaseModel):
    expo_push_token: str
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
def get_weekly_calendar(offset: int = 0):
    """
    offset = 0 => This Week
    offset = 1 => Next Week
    offset = -1 => Last Week
    """
    from db import client as mongo_client
    calendar_coll = mongo_client["hypewave"]["calendar_cache"]

    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    target_week = (monday + timedelta(weeks=offset)).date().isoformat()

    doc = calendar_coll.find_one({"week_of": target_week})
    return {"calendar": doc["calendar"] if doc else []}


@app.get("/news/latest")
async def fetch_news(limit: int = 24):
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

    # ✅ Include feedback counts + status/outcome/closed_reason
    response = [
        {
            "signal_id": str(doc.get("_id")),
            "user_id": doc.get("user_id"),
            "input": doc.get("input"),
            "output": doc.get("output"),
            "created_at": doc.get("created_at"),
            "feedback": doc.get("feedback", {"up": 0, "down": 0}),
            "status": (doc.get("status") or "open"),
            "outcome": doc.get("outcome"),
            "closed_reason": doc.get("closed_reason"),
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

# ✅ New idempotent global vote endpoint
@app.post("/signals/{signal_id}/vote")
async def cast_vote(signal_id: str, vote: int = Body(..., embed=True), user=Depends(get_current_user)):
    """
    Idempotent voting:
      - vote: 1 (up) or -1 (down)
      - one record per (signal_id, user_id)
      - counters kept in signals.feedback.{up,down}
    """
    if vote not in (1, -1):
        return {"error": "vote must be 1 or -1"}

    sid = ObjectId(signal_id)
    from db import client as mongo_client
    signals_coll = mongo_client["hypewave"]["signals"]
    sig = signals_coll.find_one({"_id": sid})
    if not sig:
        return {"error": "Signal not found"}

    user_id = user["user_id"]
    existing = votes_coll.find_one({"signal_id": sid, "user_id": user_id})

    if not existing:
        # create new vote
        votes_coll.insert_one({
            "signal_id": sid,
            "user_id": user_id,
            "vote": vote,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        if vote == 1:
            signals_coll.update_one({"_id": sid}, {"$inc": {"feedback.up": 1}})
        else:
            signals_coll.update_one({"_id": sid}, {"$inc": {"feedback.down": 1}})
    else:
        prev = existing["vote"]
        if prev != vote:
            # flip vote
            if prev == 1 and vote == -1:
                signals_coll.update_one({"_id": sid}, {"$inc": {"feedback.up": -1, "feedback.down": 1}})
            elif prev == -1 and vote == 1:
                signals_coll.update_one({"_id": sid}, {"$inc": {"feedback.down": -1, "feedback.up": 1}})
            votes_coll.update_one({"_id": existing["_id"]}, {"$set": {"vote": vote, "updated_at": datetime.now(timezone.utc)}})
        # else: same vote → no-op

    latest = signals_coll.find_one({"_id": sid}, {"feedback": 1})
    fb = latest.get("feedback", {"up": 0, "down": 0})
    return {"ok": True, "feedback": fb}

@app.post("/analyze-economic")
async def analyze_economic(payload: dict = Body(...)):
    """
    Analyze a single economic calendar item and return a concise, tradable summary.
    Accepts either:
      - { "prompt": "<full prompt string>" }
      - or fields: { title, date, time, period, forecast, previous, actual }
    Returns: { "analysis": str }
    """
    # pull fields
    title    = (payload.get("title") or "").strip()
    date     = (payload.get("date") or "").strip()
    time_    = (payload.get("time") or "").strip()
    period   = (payload.get("period") or "").strip()
    forecast = (payload.get("forecast") or "").strip()
    previous = (payload.get("previous") or "").strip()
    actual   = (payload.get("actual") or "").strip()
    user_prompt = payload.get("prompt")

    # build a compact, instruction‑driven prompt when none provided
    if not user_prompt:
        lines = [
            "You are Hypewave AI. Analyze an economic data release for traders.",
            "",
            f"Release: {title or 'N/A'}",
            f"Date: {date or 'N/A'}",
            f"Time: {time_ or 'N/A'}",
            f"Period: {period}" if period else None,
            f"Forecast: {forecast}" if forecast else None,
            f"Previous: {previous}" if previous else None,
            f"Actual: {actual}" if actual else None,
            "",
            "Write a SHORT, crisp take (no long paragraphs). Use 1-3 bullets max:",
            "• Why markets care (which assets most sensitive: rates, USD, equities, oil, gold).",
            "• Over vs under forecast: likely immediate reactions.",
            "• What details matter (core vs headline, revisions, subcomponents).",
            "• (If helpful) 1‑line historical/seasonal context.",
            "",
            "Constraints:",
            "- Keep it under ~120 words.",
            "- No fluff, no generic disclaimers.",
            "- Prefer concrete mappings (e.g., 'hotter CPI → ↑yields/↑USD/↓gold').",
        ]
        user_prompt = "\n".join([l for l in lines if l is not None])

    # call your existing OpenAI client (same style as /chat)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Hypewave AI: concise, market‑savvy, and specific."},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=320,   # tight: we want short output
            temperature=0.4,  # crisp + deterministic
        )
        text = (resp.choices[0].message.content or "").strip()
        # final safety clamp: if model returned something long, trim politely
        if len(text.split()) > 140:
            words = text.split()[:140]
            text = " ".join(words) + " …"
        return {"analysis": text}
    except Exception as e:
        # bubble up a friendly error
        return {"analysis": None, "error": str(e)}
    
@app.post("/me/push-token")
async def save_push_token(body: PushTokenBody, user=Depends(get_current_user)):
    """
    Saves the caller's Expo push token on their user record.
    Call this from the app after registerForPushNotificationsAsync().
    """
    try:
        set_user_push_token(user["user_id"], body.expo_push_token)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/signals/winrate")
def get_global_winrate():
    return get_winrate()
