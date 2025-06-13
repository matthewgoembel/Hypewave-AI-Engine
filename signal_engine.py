# signal_engine.py

from typing import List
from db import log_alert
from market_data_ws import get_latest_ohlc
from pattern_detection import detect_all_patterns

TIMEFRAMES = ["15m", "1h", "4h"]

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = set()

    for tf in TIMEFRAMES:
        candles = get_latest_ohlc(f"{symbol}USDT", tf)
        if not candles or len(candles) < 20:
            continue

        patterns = detect_all_patterns(candles, symbol, tf)
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
