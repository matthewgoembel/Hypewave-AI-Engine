# signal_engine.py

from typing import List
from market_context import get_market_context
from db import log_alert
from market_data_ws import get_latest_ohlc
from pattern_detection import (
    detect_fvg,
    detect_order_block,
    detect_bos,
    detect_equal_highs_lows,
    detect_prev_day_levels,
    detect_equilibrium_tap,
    detect_divergence,
    detect_volume_spike
)

pattern_funcs = [
    detect_fvg,
    detect_order_block,
    detect_bos,
    detect_equal_highs_lows,
    detect_prev_day_levels,
    detect_equilibrium_tap,
    detect_divergence,
    detect_volume_spike
]

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = []
    context = get_market_context(f"${symbol}")

    # Optional: Sentiment-based alerts
    if "Funding Rate" in context and "0." in context:
        msg = f"{symbol}: Elevated funding rate detected. Possible squeeze setup."
        log_alert("auto", {"symbol": symbol}, {"result": msg, "source": "auto-alert"})
        alerts.append(msg)

    if "Fear" in context and "Greed" in context:
        msg = f"{symbol}: Sentiment extreme detected. Proceed with caution."
        log_alert("auto", {"symbol": symbol}, {"result": msg, "source": "auto-alert"})
        alerts.append(msg)

    # Pattern detection on multiple timeframes
    for tf in ["15m", "1h", "4h"]:
        ohlc = get_latest_ohlc(f"{symbol}USDT", tf)
        if not ohlc:
            continue

        for func in pattern_funcs:
            results = func(ohlc, symbol)
            for pattern in results:
                emoji = "🔴" if "bearish" in pattern['note'].lower() else "🔵"
                price = ohlc.get("close", "N/A")
                msg = f"{emoji} ${symbol} | {pattern['note']} | {tf} | Price: {price}"
                log_alert("auto", {"symbol": symbol}, {
                    "result": msg,
                    "source": pattern["pattern"],
                    "timeframe": tf,
                    "confidence": pattern.get("confidence", 70)
                })
                alerts.append(msg)

    return alerts
