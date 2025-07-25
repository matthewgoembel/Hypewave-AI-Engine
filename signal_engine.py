# === signal_engine.py (refactored) ===

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from openai import OpenAI

from db import log_signal, client as mongo_client
from market_data_ws import get_latest_ohlc

client = OpenAI()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

TIMEFRAMES = ["5m", "15m", "1h", "4h"]
CONFIDENCE_THRESHOLD = 60
signals_coll = mongo_client["hypewave"]["signals"]
signal_control_coll = mongo_client["hypewave"]["signal_control"]

def should_skip_symbol(symbol: str) -> bool:
    entry = signal_control_coll.find_one({"symbol": symbol})
    now = datetime.now(timezone.utc)

    next_check = entry.get("next_check_at") if entry else None
    if next_check and next_check.tzinfo is None:
        next_check = next_check.replace(tzinfo=timezone.utc)

    return next_check and now < next_check


def update_signal_control(symbol: str, status: str, notes: str, next_check_minutes: int):
    now = datetime.now(timezone.utc)
    control_entry = {
        "symbol": symbol,
        "last_check": now,
        "next_check_at": now + timedelta(minutes=next_check_minutes),
        "last_status": status,
        "notes": notes
    }
    signal_control_coll.update_one(
        {"symbol": symbol},
        {"$set": control_entry},
        upsert=True
    )

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()
    if should_skip_symbol(symbol):
        logger.info("[⏳] Skipping %s — still in cooldown.", symbol)
        return []

    candles_by_tf = {}
    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles or len(candles) < 10:
            logger.warning("[⚠️] Insufficient candles for %s %s", symbol, tf)
            continue
        candles_by_tf[tf] = candles

    if not candles_by_tf:
        return []

    try:
        result = evaluate_trade_opportunity(symbol, candles_by_tf)
        if result["trade"] == "NONE":
            logger.info("[🛑] No trade for %s. Next check in %s min.", symbol, result["next_check"])
            update_signal_control(symbol, "no_trade", result["thesis"], result["next_check"])
            return []

        recent = signals_coll.find_one(
            {"input.symbol": symbol, "output.trade": result["trade"]},
            sort=[("created_at", -1)]
        )

        skip_due_to_duplicate = False
        if recent:
            last_entry = recent["output"].get("entry")
            last_time = recent["created_at"].replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
            close_price = abs(result["entry"] - last_entry) / last_entry * 100 < 0.2 if last_entry and result["entry"] else False
            skip_due_to_duplicate = age_minutes < 5 and close_price

        if skip_due_to_duplicate:
            logger.info("[⚠️] Duplicate trade skipped for %s.", symbol)
            return []

        log_signal("partner-ai", {"symbol": symbol}, {
            "result": f"${symbol} | {result['trade']} | {result['timeframe']} | Entry: {result['entry']} | Conf: {result['confidence']}",
            "source": "AI Multi-Timeframe Engine",
            "timeframe": result["timeframe"],
            "confidence": result["confidence"],
            "entry": result["entry"],
            "sl": result["sl"],
            "tp": result["tp"],
            "thesis": result["thesis"],
            "trade": result["trade"]
        }, extra_meta={"status": "OPEN"})

        update_signal_control(symbol, "trade", result["thesis"], result["next_check"])
        alerts.add(result["thesis"])

    except Exception as e:
        logger.exception("[❌ Error evaluating signal for %s]", symbol)

    return list(alerts)

def evaluate_trade_opportunity(symbol: str, candles_by_tf: dict) -> dict:
    prompt = f"""
You are a professional AI market analyst. Review these OHLC candles across 5m, 15m, 1h, and 4h timeframes. Identify the best high-probability trade if one exists.
Respond ONLY with swing or scalp trades worth taking, or NONE if the market is consolidating.

Use this exact format:
**Trade:** LONG / SHORT / NONE  
**Confidence:** [0-100]  
**Timeframe:** 5m / 15m / 1h / 4h / multi  
**Entry:** [price or N/A]  
**Stop Loss:** [price or N/A]  
**Take Profit:** [price or N/A]  
**Next Check In Minutes:** [e.g. 12, 30, 240]  
**Thesis:** [brief rationale]
""".strip() + f"\n\n{candles_by_tf}"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a highly accurate trading assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=800
    )

    raw = response.choices[0].message.content.strip()
    logger.info("[GPT] %s", raw)

    def extract(pattern):
        match = re.search(pattern, raw, re.IGNORECASE)
        return match.group(1).strip() if match else None

    trade = extract(r"\*\*Trade:\*\*\s*(LONG|SHORT|NONE)") or "NONE"
    confidence = int(extract(r"\*\*Confidence:\*\*\s*(\d+)") or 0)
    timeframe = extract(r"\*\*Timeframe:\*\*\s*(\w+)") or "multi"
    entry = float(extract(r"\*\*Entry:\*\*\s*([\d\.]+)") or 0)
    sl = float(extract(r"\*\*Stop Loss:\*\*\s*([\d\.]+)") or 0)
    tp = float(extract(r"\*\*Take Profit:\*\*\s*([\d\.]+)") or 0)
    next_check = int(extract(r"\*\*Next Check In Minutes:\*\*\s*(\d+)") or 60)
    thesis = extract(r"\*\*Thesis:\*\*\s*(.+)") or "No reason provided."

    return {
        "trade": trade.upper(),
        "confidence": confidence,
        "timeframe": timeframe,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "next_check": next_check,
        "thesis": thesis
    }
