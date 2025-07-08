# signal_engine.py

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List
from openai import OpenAI

from db import log_signal, client as mongo_client
from market_data_ws import get_latest_ohlc

client = OpenAI()

# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Optional: attach a console handler if running standalone
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

TIMEFRAMES = ["5m", "15m", "1h", "4h"]
CONFIDENCE_THRESHOLD = 60

# Reuse Mongo collection
signals_coll = mongo_client["hypewave"]["signals"]


def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()
    candles_by_tf = {}

    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles:
            logger.warning("[⚠️] No candles for %s %s", symbol, tf)
            continue
        if len(candles) < 10:
            logger.warning("[⚠️] Not enough candles (%d) for %s %s", len(candles), symbol, tf)
            continue
        candles_by_tf[tf] = candles

    if not candles_by_tf:
        logger.warning("[⚠️] No valid candles collected for %s.", symbol)
        return list(alerts)

    logger.info("[🧠 Evaluating multi-timeframe setup] %s", symbol)

    try:
        trade = evaluate_multi_timeframe_opportunity(symbol, candles_by_tf)
        if not trade:
            logger.info("[❌] No confident trade returned.")
            return list(alerts)

        # Check for duplicate recent signals (same trade type within 5 min and ~0.2% entry)
        recent = signals_coll.find_one(
            {
                "input.symbol": symbol,
                "output.trade": trade["trade"],
            },
            sort=[("created_at", -1)]
        )

        skip_due_to_duplicate = False
        if recent:
            last_entry = recent["output"].get("entry")
            last_time = recent["created_at"]

            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)

            age_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
            is_recent = age_minutes < 5
            is_close_price = (
                isinstance(last_entry, (int, float)) and
                isinstance(trade["entry"], (int, float)) and
                abs(trade["entry"] - last_entry) / last_entry * 100 < 0.2
            )

            if is_recent and is_close_price:
                skip_due_to_duplicate = True

        if skip_due_to_duplicate:
            logger.info("[⚠️] Skipping duplicate signal.")
            return list(alerts)

        # Log signal
        msg = (
            f"${symbol} | {trade['trade']} | MULTI | "
            f"Entry: {trade['entry']} | Conf: {trade['confidence']}"
        )
        log_signal(
            "partner-ai",
            {"symbol": symbol},
            {
                "result": msg,
                "source": "AI Multi-Timeframe Engine",
                "timeframe": "multi",
                "confidence": trade["confidence"],
                "entry": trade["entry"],
                "sl": trade["sl"],
                "tp": trade["tp"],
                "thesis": trade["thesis"],
                "trade": trade["trade"]
            }
        )
        alerts.add(msg)
        logger.info("[✅ TRADE] %s", trade)

        # Clean up old signals
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        deleted = signals_coll.delete_many({"created_at": {"$lt": cutoff}})
        if deleted.deleted_count > 0:
            logger.info("[🧹] Deleted %d old signals.", deleted.deleted_count)

    except Exception as e:
        logger.exception("[❌ Error processing multi-timeframe for %s]", symbol)

    return list(alerts)



def evaluate_multi_timeframe_opportunity(symbol, candles_by_tf) -> dict:
    from db import trades_review

    prompt = f"""
You are a professional trader. Analyze the following OHLC candles across multiple timeframes (4h, 1h, 15m, 5m) and determine the single highest-probability trade setup.

Timeframes and candles:
{candles_by_tf}

Respond ONLY if there is a setup with >{CONFIDENCE_THRESHOLD}% probability.

🎯 Respond EXACTLY in this format:

**Trade:** LONG or SHORT
**Confidence:** [0–100]
**Entry:** [price]
**Stop Loss:** [price]
**Take Profit:** [price]
**Thesis:** [1–2 sentences why]
""".strip()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a highly accurate trading assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=700
    )

    raw = response.choices[0].message.content.strip()
    logger.info("[🔍 GPT Raw Output] %s", raw)

    if not raw or "confidence" not in raw.lower():
        trades_review.insert_one({
            "symbol": symbol,
            "timeframe": "multi",
            "raw_output": raw,
            "parsed_trade": None,
            "accepted": False,
            "timestamp": datetime.now(timezone.utc)
        })
        return None

    trade = {
        "trade": "N/A",
        "confidence": 0,
        "entry": "—",
        "sl": "—",
        "tp": "—",
        "thesis": "—"
    }

    try:
        trade_match = re.search(r"\*\*Trade:\*\*\s*(LONG|SHORT)", raw, re.IGNORECASE)
        conf_match = re.search(r"\*\*Confidence:\*\*\s*(\d+)", raw, re.IGNORECASE)
        entry_match = re.search(r"\*\*Entry:\*\*\s*([\d\.]+)", raw, re.IGNORECASE)
        sl_match = re.search(r"\*\*Stop Loss:\*\*\s*([\d\.]+)", raw, re.IGNORECASE)
        tp_match = re.search(r"\*\*Take Profit:\*\*\s*([\d\.]+)", raw, re.IGNORECASE)
        thesis_match = re.search(r"\*\*Thesis:\*\*\s*(.+)", raw, re.IGNORECASE)

        if trade_match:
            trade["trade"] = trade_match.group(1).upper()
        if conf_match:
            trade["confidence"] = int(conf_match.group(1))
        if entry_match:
            trade["entry"] = float(entry_match.group(1))
        if sl_match:
            trade["sl"] = float(sl_match.group(1))
        if tp_match:
            trade["tp"] = float(tp_match.group(1))
        if thesis_match:
            trade["thesis"] = thesis_match.group(1).strip()
    except Exception as e:
        logger.exception("[❌ Parsing error]")
        trades_review.insert_one({
            "symbol": symbol,
            "timeframe": "multi",
            "raw_output": raw,
            "parsed_trade": None,
            "accepted": False,
            "timestamp": datetime.now(timezone.utc)
        })
        return None

    trades_review.insert_one({
        "symbol": symbol,
        "timeframe": "multi",
        "raw_output": raw,
        "parsed_trade": trade,
        "accepted": trade["confidence"] and trade["confidence"] >= CONFIDENCE_THRESHOLD,
        "timestamp": datetime.now(timezone.utc)
    })

    if trade["confidence"] and trade["confidence"] >= CONFIDENCE_THRESHOLD:
        return trade
    else:
        logger.info("[⚠️ Discarded Low-Confidence Trade] %s", trade)
        return None