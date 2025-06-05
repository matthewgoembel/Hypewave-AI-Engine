# pattern_detection.py

# This is a mock prototype of your pattern detection engine.
# Each function will eventually use real OHLC data — for now it returns sample results.

from typing import Tuple, List

# Utility result format
def result(pattern: str, timeframe: str, symbol: str, note: str) -> dict:
    return {
        "symbol": symbol,
        "pattern": pattern,
        "timeframe": timeframe,
        "note": note,
        "confidence": 75
    }

# Fair Value Gap (FVG)
def detect_fvg(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("FVG", "15m", symbol, "Bullish FVG tapped after impulse move"),
        result("FVG", "1h", symbol, "Bearish FVG forming on rejection")
    ]

# Order Block (OB)
def detect_order_block(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Order Block", "5m", symbol, "Bullish OB formed before breakout")
    ]

# Break of Structure (BOS)
def detect_bos(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Break of Structure", "1h", symbol, "BOS confirmed above previous high")
    ]

# Equal Highs / Lows
def detect_equal_highs_lows(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Equal Highs", "15m", symbol, "Double top / equal highs"),
        result("Equal Lows", "1h", symbol, "Liquidity resting below equal lows")
    ]

# Previous Day High/Low + Confluence
def detect_prev_day_levels(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Prev Day High + SFP", "1h", symbol, "Sweep of yesterday's high with rejection"),
        result("Prev Day Low + EQ", "15m", symbol, "Tap into previous low + equilibrium")
    ]

# Equilibrium Zone Taps
def detect_equilibrium_tap(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Equilibrium", "1h", symbol, "Price tapped EQ zone around 50% of range")
    ]

# Divergence Detection
def detect_divergence(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Bullish Divergence", "15m", symbol, "Lower price, higher RSI")
    ]

# High Volume Moves
def detect_volume_spike(ohlc: dict, symbol: str) -> List[dict]:
    return [
        result("Volume Spike", "5m", symbol, "Massive candle with volume breakout")
    ]
