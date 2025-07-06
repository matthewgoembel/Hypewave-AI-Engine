import base64, subprocess, os
from openai import OpenAI
from datetime import datetime
from typing import List
from db import log_signal  # ✅ Use correct logger for trade signals
from market_data_ws import get_latest_ohlc, build_market_context
from pattern_detection import detect_all_patterns, group_patterns_by_bias
from utils import capture_chart, encode_chart_to_base64  # ✅ Consolidated helpers

TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]
client = OpenAI()

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()

    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles or len(candles) < 10:
            continue

        patterns = detect_all_patterns(candles, symbol, tf)
        if not patterns:
            continue

        grouped = group_patterns_by_bias(patterns)
        # Instead of requiring 3 same-bias, allow ANY confluences
        total_signals = sum(len(v) for v in grouped.values())

        if total_signals == 0:
            continue

        # Determine the most likely direction (majority vote)
        bullish_count = len(grouped["bullish"])
        bearish_count = len(grouped["bearish"])

        if bullish_count > bearish_count:
            direction = "long"
        elif bearish_count > bullish_count:
            direction = "short"
        else:
            # If tie or all neutral, skip
            print(f"[ℹ️] No clear bias for {symbol} {tf}, skipping.")
            continue

        market_context = build_market_context(symbol, tf, candles, patterns)

        print(f"[🧠 Evaluating] {symbol} {tf} → {direction.upper()} ({total_signals} signals)")

        trade = evaluate_trade_opportunity(
            symbol=symbol,
            timeframe=tf,
            candles=candles,
            patterns=patterns,
            market_context=market_context,
            direction=direction
        )

        if trade:
            print("[✅ TRADE]", trade)
            msg = f"${symbol} | {trade['trade']} | {tf} | Entry: {trade['entry']} | Conf: {trade['confidence']}"
            log_signal("partner-ai", {"symbol": symbol}, {
                "result": msg,
                "source": "AI Confluence Engine",
                "timeframe": tf,
                "confidence": trade["confidence"],
                "entry": trade["entry"],
                "sl": trade["sl"],
                "tp": trade["tp"],
                "thesis": trade["thesis"]
            })
            alerts.add(msg)
        else:
            print("[❌] No confident trade returned.")

    return list(alerts)


def evaluate_trade_opportunity(symbol, timeframe, candles, patterns, market_context, direction) -> dict:
    from db import trades_review  # <-- import the collection here

    import re

    chart_path = capture_chart(symbol, timeframe)
    if not chart_path:
        print(f"[⚠️] Chart not available, skipping AI evaluation for {symbol} {timeframe}")
        return None

    base64_chart = encode_chart_to_base64(chart_path)
    try:
        confluences = "\n".join([
            f"- {p['pattern']} | {p['note']} | Confidence: {p['confidence']}"
            for p in patterns if p['bias'] == direction or p['bias'] == "neutral"
        ])

        context_summary = (
            f"Symbol: {market_context['symbol']}\n"
            f"Timeframe: {market_context['timeframe']}\n"
            f"Trend: {market_context['trend']}\n"
            f"Current Price: {market_context['current_price']}\n"
            f"Structure:\n"
            f"  • Support: {market_context['structure']['support']}\n"
            f"  • Resistance: {market_context['structure']['resistance']}\n"
            f"Last Candle: {market_context['last_candle']['type']} ({market_context['last_candle']['size']})\n"
            f"Volume: {market_context['last_candle']['volume']}\n"
        )

        prompt = f"""
        You are Hypewave AI, a professional trader working alongside the user.

        Evaluate this potential trade setup like a skilled discretionary trader. 
        Carefully analyze the chart image, the pattern signals, and the market context. 
        You should think critically about the risk and probability of success.

        Only provide a trade idea if you sincerely believe there is at least a 60% probability 
        that the setup will play out as expected over the next few candles. 
        If no such opportunity exists, respond with nothing at all.

        🧠 Confluence signals for {symbol} on {timeframe} timeframe:
        {confluences}

        📊 Market Context:
        {context_summary}

        🎯 When you are confident, respond EXACTLY in this format (no extra commentary):

        **Trade:** LONG or SHORT  
        **Confidence:** [number 0–100]  
        **Entry:** [price level]  
        **Stop Loss:** [price level]  
        **Take Profit:** [price level]  
        **Thesis:** [1–2 sentences explaining why this setup is strong]
        """.strip()

        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {"role": "system", "content": "You are a highly accurate trading assistant. Only respond if the chart confirms a strong setup."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{base64_chart}",
                            "detail": "high"
                        }}
                    ]
                }
            ],
            max_tokens=600
        )

        raw = response.choices[0].message.content.strip()
        print("[🔍 GPT Raw Output]", raw)

        if not raw or "confidence" not in raw.lower():
            # Log anyway for backtesting
            trades_review.insert_one({
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "raw_output": raw,
                "parsed_trade": None,
                "accepted": False,
                "timestamp": datetime.utcnow()
            })
            return None

        # Regex patterns for robust parsing
        trade = {
            "trade": None,
            "confidence": None,
            "entry": None,
            "sl": None,
            "tp": None,
            "thesis": ""
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

        # Log all evaluations for backtest
        trades_review.insert_one({
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "raw_output": raw,
            "parsed_trade": trade,
            "accepted": trade["confidence"] and trade["confidence"] >= 60,
            "timestamp": datetime.utcnow()
        })

        if trade["confidence"] and trade["confidence"] >= 60:
            return trade
        else:
            print("[⚠️ Discarded Low-Confidence Trade]", trade)
            return None

    except Exception as e:
        print(f"[❌ AI Evaluation Error] {e}")
        return None
