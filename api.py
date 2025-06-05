from fastapi import FastAPI, Query, UploadFile, File, Form, Body
from fastapi import BackgroundTasks
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
from twitter_fetcher import run_loop as twitter_run_loop
from twitter_fetcher import get_latest_saved_tweets
from signal_engine import generate_alerts_for_symbol
from auto_signal_runner import start_signal_engine
from market_data_ws import start_ws_listener 
import base64, random, os, re, threading


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

@app.on_event("startup")
def start_twitter_fetcher():
    threading.Thread(target=lambda: twitter_run_loop(60), daemon=True).start()


@app.get("/")
def root():
    return {"message": "Hypewave AI is live 🚀"}

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

        # 1. Try to extract a trading symbol (e.g. $BTC, ETH, NASDAQ)
        import re
        match = re.search(r"\$?([A-Z]{2,6})", input.upper())
        symbol = match.group(1) if match else "BTC"  # Default to BTC if none found

        # 2. Load context + latest pattern data
        is_setup = is_trade_setup_question(task["prompt"])
        market_context = get_market_context(input)
        pattern_signals = generate_alerts_for_symbol(symbol)

        # Format as bullet list
        formatted_signals = "\n".join([f"- {s}" for s in pattern_signals[:5]])  # Limit to 5

        # 3. Build dynamic system prompt
        if not is_setup and intent_data["intent"] in ("chat", "trader_chat"):
            system_prompt = (
                f"You are Hypewave AI, a trading expert and partner of the user.\n"
                f"You are striving for a perfect winrate — something only a machine could pull off.\n"
                f"Whenever you are given a question or prompt, NEVER refer to yourself as an AI, and never say 'As an AI, I can't'.\n"
                f"You are a trader. Be confident, tactical, and specific.\n"
                f"You offer the bullish and bearish scenarios, but always help guide the user as if they are your trading partner.\n\n"
                f"**Live Chart Signals for ${symbol}:**\n"
                f"{formatted_signals}\n\n"
                f"**Sentiment & Macro Context:**\n"
                f"{market_context}\n\n"
                f"🧠 Format your answers with:\n"
                f"- Bullet points\n"
                f"- Headers if helpful\n"
                f"- Bolded key terms (e.g. FVG, BOS, SFP)\n"
                f"- NEVER one giant paragraph."
            )
        else:
            system_prompt = (
                task["system_prompt"]
                + f"\n\n**Live Chart Signals for ${symbol}:**\n{formatted_signals}"
                + f"\n\n**Market Context:**\n{market_context}"
            )

        # 4. Build GPT messages
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

        # 5. Send to OpenAI
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
\


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
        return get_latest_saved_tweets(limit=limit)
    except Exception as e:
        return {"error": str(e)}

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

@app.post("/webhook/tradingview")
async def tradingview_webhook(payload: dict = Body(...)):
    try:
        symbol = payload.get("symbol", "UNKNOWN")
        event = payload.get("event", "alert")
        price = payload.get("price", "N/A")
        note = payload.get("note", "")

        msg = f"📢 ${symbol} TradingView Alert — {event.upper()} @ ${price} — {note}"
        log_alert("tv_webhook", {"symbol": symbol}, {"result": msg, "source": "tradingview"})

        return {"status": "ok", "message": msg}
    except Exception as e:
        return {"error": str(e)}

@app.on_event("startup")
def on_startup():
    start_signal_engine()
    start_ws_listener()  # ✅ This ensures Binance WS starts