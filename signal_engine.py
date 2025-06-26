import base64, subprocess, os
from openai import OpenAI
from datetime import datetime
from typing import List
from db import log_alert
from market_data_ws import get_latest_ohlc, build_market_context
from pattern_detection import detect_all_patterns, group_patterns_by_bias

# Match these with your WebSocket scanner config
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]

client = OpenAI()

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()

    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles or len(candles) < 20:
            continue

        # 1. Detect patterns
        patterns = detect_all_patterns(candles, symbol, tf)
        if not patterns:
            continue

        # 2. Group by bias
        grouped = group_patterns_by_bias(patterns)

        # 3. Check for confluence
        direction = None
        if len(grouped["bullish"]) >= 3:
            direction = "long"
        elif len(grouped["bearish"]) >= 3:
            direction = "short"

        # 4. Build context
        market_context = build_market_context(symbol, tf, candles, patterns)

        # 5. Evaluate trade if high-confidence confluence
        if direction:
            print(f"[🔥 CONFLUENCE] {symbol} {tf} → {direction.upper()} with {len(grouped[direction if direction == 'long' else 'bearish'])} patterns")

            # 🔮 Use your AI partner to analyze trade
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
                log_alert("partner-ai", {"symbol": symbol}, {
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

        # 6. Log all raw patterns as basic alerts (optional redundancy)
        for p in patterns:
            msg = f"${symbol} | {p['note']} | {tf} | Price: {candles[-1]['close']}"
            if msg not in alerts:
                log_alert("auto", {"symbol": symbol}, {
                    "result": msg,
                    "source": p["pattern"],
                    "timeframe": tf,
                    "confidence": p.get("confidence", 70)
                })
                alerts.add(msg)

    return list(alerts)

def evaluate_trade_opportunity(symbol, timeframe, candles, patterns, market_context, direction) -> dict:
    from utils import capture_chart, encode_chart_to_base64, extract_bias_intent_timeframe


    # Generate chart image from TradingView
    chart_path = capture_chart(symbol, timeframe)
    if not chart_path:
        print(f"[⚠️] Chart not available, skipping AI evaluation for {symbol} {timeframe}")
        return None

    base64_chart = encode_chart_to_base64(chart_path)
    try:
        # 1. Format pattern confluence
        confluences = "\n".join([
            f"- {p['pattern']} | {p['note']} | Confidence: {p['confidence']}"
            for p in patterns if p['bias'] == direction or p['bias'] == "neutral"
        ])

        # 2. Format market context
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

        # 3. GPT prompt
        prompt = f"""
            You are Hypewave AI, a professional trading strategist.

            You **only respond** if the trade setup is highly confident. If the setup is weak or unclear, say **nothing at all** — no commentary, no explanations.

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

        # 4. GPT call
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
            return None  # GPT stayed silent (as instructed)

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

        # 5. Enforce confidence filter
        if trade["confidence"] and trade["confidence"] >= 60:
            return trade
        else:
            return None

    except Exception as e:
        print(f"[❌ AI Evaluation Error] {e}")
        return None

def capture_chart(symbol: str, timeframe: str) -> str:
    """
    Calls the Puppeteer script to capture a chart screenshot.
    Returns the path to the saved PNG file, or None if it failed.
    """
    try:
        print(f"[📸] Capturing chart for {symbol} {timeframe}...")
        subprocess.run(["node", "hypewave-screenshot/screenshot.js", symbol, timeframe], check=True)
        path = f"media/{symbol}_{timeframe}.png"
        return path if os.path.exists(path) else None
    except Exception as e:
        print(f"[❌ Screenshot Error] {e}")
        return None

def encode_chart_to_base64(image_path: str) -> str:
    """
    Converts a PNG file to base64 for use in OpenAI Vision input.
    """
    with open(image_path, "rb") as img:
        return base64.b64encode(img.read()).decode("utf-8")