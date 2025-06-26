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
        if not candles or len(candles) < 20:
            continue

        patterns = detect_all_patterns(candles, symbol, tf)
        if not patterns:
            continue

        grouped = group_patterns_by_bias(patterns)
        direction = None
        if len(grouped["bullish"]) >= 3:
            direction = "long"
        elif len(grouped["bearish"]) >= 3:
            direction = "short"

        market_context = build_market_context(symbol, tf, candles, patterns)

        if direction:
            print(f"[🔥 CONFLUENCE] {symbol} {tf} → {direction.upper()} with {len(grouped[direction if direction == 'long' else 'bearish'])} patterns")

            trade = evaluate_trade_opportunity(
                symbol=symbol,
                timeframe=tf,
                candles=candles,
                patterns=patterns,
                market_context=market_context,
                direction=direction
            )

            if trade and trade.get("confidence", 0) >= 70:
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

    return list(alerts)

def evaluate_trade_opportunity(symbol, timeframe, candles, patterns, market_context, direction) -> dict:
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
            You are Hypewave AI, a professional trading strategist.

            You **only respond** if the trade setup is highly confident. If the setup is weak or unclear, say **nothing at all**.

            🧠 Confluence signals for {symbol} on {timeframe} timeframe:
            {confluences}

            📊 Market Context:
            {context_summary}

            🎯 Output ONLY if this is a highly confident {direction.upper()} setup. Format:

            **Trade:** LONG or SHORT  
            **Confidence:** ___  
            **Entry:** ___  
            **Stop Loss:** ___  
            **Take Profit:** ___  
            **Thesis:** [why this setup is excellent]
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
        if not raw or "confidence" not in raw.lower():
            return None

        lines = raw.splitlines()
        trade = {
            "trade": None,
            "confidence": None,
            "entry": None,
            "sl": None,
            "tp": None,
            "thesis": ""
        }

        for line in lines:
            line = line.strip()
            if line.lower().startswith("**trade:**"):
                trade["trade"] = "LONG" if "long" in line.lower() else "SHORT"
            elif line.lower().startswith("**confidence:**"):
                trade["confidence"] = int(''.join(filter(str.isdigit, line)))
            elif line.lower().startswith("**entry:**"):
                trade["entry"] = float(''.join(filter(lambda c: c.isdigit() or c == '.', line)))
            elif line.lower().startswith("**stop loss:**"):
                trade["sl"] = float(''.join(filter(lambda c: c.isdigit() or c == '.', line)))
            elif line.lower().startswith("**take profit:**"):
                trade["tp"] = float(''.join(filter(lambda c: c.isdigit() or c == '.', line)))
            elif line.lower().startswith("**thesis:**"):
                trade["thesis"] = line.split("**thesis:**", 1)[-1].strip()

        if trade["confidence"] and trade["confidence"] >= 60:
            return trade
        else:
            return None

    except Exception as e:
        print(f"[❌ AI Evaluation Error] {e}")
        return None
