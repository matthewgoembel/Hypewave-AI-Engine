# signal_engine.py

from openai import OpenAI
from datetime import datetime, timezone
from typing import List
from db import log_signal

from market_data_ws import get_latest_ohlc

client = OpenAI()
TIMEFRAMES = ["5m", "15m", "1h", "4h"]

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()

    # Import Mongo for duplicate detection
    from db import client as mongo_client
    signals_coll = mongo_client["hypewave"]["signals"]

    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles or len(candles) < 10:
            continue

        print(f"[🧠 Evaluating] {symbol} {tf}")

        trade = evaluate_trade_opportunity(symbol, tf, candles)
        if trade:
            # ✅ Check for duplicate recent signals
            recent = signals_coll.find_one(
                {
                    "input.symbol": symbol,
                    "output.timeframe": tf,
                    "output.trade": trade["trade"],
                },
                sort=[("created_at", -1)]
            )

            skip_due_to_duplicate = False

            if recent:
                last_entry = recent["output"].get("entry")
                last_time = recent["created_at"]
                age_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60

                if (
                    age_minutes < 5
                    and isinstance(last_entry, (int, float))
                    and isinstance(trade["entry"], (int, float))
                ):
                    pct_diff = abs(trade["entry"] - last_entry) / last_entry * 100
                    if pct_diff < 0.2:
                        skip_due_to_duplicate = True

            if skip_due_to_duplicate:
                print("[⚠️] Skipping duplicate signal.")
                continue

            # ✅ Log signal
            msg = (
                f"${symbol} | {trade['trade']} | {tf} | "
                f"Entry: {trade['entry']} | Conf: {trade['confidence']}"
            )
            log_signal("partner-ai", {"symbol": symbol}, {
                "result": msg,
                "source": "AI Candle Engine",
                "timeframe": tf,
                "confidence": trade["confidence"],
                "entry": trade["entry"],
                "sl": trade["sl"],
                "tp": trade["tp"],
                "thesis": trade["thesis"],
                "trade": trade["trade"]  # Save direction for dedupe
            })
            alerts.add(msg)
            print(f"[✅ TRADE] {trade}")
        else:
            print("[❌] No confident trade returned.")

    return list(alerts)


def evaluate_trade_opportunity(symbol, timeframe, candles) -> dict:
    from db import trades_review
    import re

    prompt = f"""
You are a professional trader. Analyze the following raw OHLC candles and decide whether there is a high-probability trade setup.

Respond ONLY if there is a setup with >60% probability.

Candle Data (latest last):
{candles}

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
        max_tokens=600
    )

    raw = response.choices[0].message.content.strip()
    print("[🔍 GPT Raw Output]", raw)

    if not raw or "confidence" not in raw.lower():
        trades_review.insert_one({
            "symbol": symbol,
            "timeframe": timeframe,
            "raw_output": raw,
            "parsed_trade": None,
            "accepted": False,
            "timestamp": datetime.now(timezone.utc)
        })
        return None

    # Parse
    trade = {
        "trade": "N/A",
        "confidence": 0,
        "entry": "—",
        "sl": "—",
        "tp": "—",
        "thesis": "—"
    }

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

    trades_review.insert_one({
        "symbol": symbol,
        "timeframe": timeframe,
        "raw_output": raw,
        "parsed_trade": trade,
        "accepted": trade["confidence"] and trade["confidence"] >= 60,
        "timestamp": datetime.now(timezone.utc)
    })

    if trade["confidence"] and trade["confidence"] >= 60:
        return trade
    else:
        print("[⚠️ Discarded Low-Confidence Trade]", trade)
        return None
