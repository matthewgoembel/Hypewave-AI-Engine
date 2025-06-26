# pattern_detection.py

from typing import List, Dict
import statistics

# --- Shared utility for formatting results ---
def result(pattern: str, timeframe: str, symbol: str, note: str, confidence: int = 75, bias: str = "neutral") -> dict:
    return {
        "symbol": symbol,
        "pattern": pattern,
        "timeframe": timeframe,
        "note": note,
        "confidence": confidence,
        "bias": bias
    }

# --- Fair Value Gap Detection (basic logic) ---
def detect_fvg(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 3:
        return results

    for i in range(2, len(candles)):
        c1 = candles[i - 2]
        c2 = candles[i - 1]
        c3 = candles[i]

        if c2["low"] > c1["high"]:  # Bullish FVG (gap between candles)
            results.append(result("Bullish FVG", tf, symbol, "Bullish FVG formed", 78, bias="bullish"))
        elif c2["high"] < c1["low"]:  # Bearish FVG
            results.append(result("Bearish FVG", tf, symbol, "Bearish FVG formed", 78, bias="bearish"))


    return results

# --- Basic RSI Divergence Detector (fake RSI + divergence) ---
def detect_divergence(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 15:
        return results

    prices = [c["close"] for c in candles[-14:]]
    rsis = compute_rsi(prices)

    if len(rsis) < 2:
        return results

    if prices[-1] < prices[-2] and rsis[-1] > rsis[-2]:  # Bullish div
        results.append(result("Bullish Divergence", tf, symbol, "Lower price, higher RSI", 80, bias="bullish"))
    elif prices[-1] > prices[-2] and rsis[-1] < rsis[-2]:  # Bearish div
        results.append(result("Bearish Divergence", tf, symbol, "Higher price, lower RSI", 80, bias="bearish"))

    return results

def compute_rsi(prices: List[float], period: int = 14) -> List[float]:
    if len(prices) < period + 1:
        return []

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = statistics.mean(gains[:period])
    avg_loss = statistics.mean(losses[:period])
    rsis = []

    for i in range(period, len(prices) - 1):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        rsis.append(rsi)

    return rsis

# --- Break of Structure (basic swing high breakout) ---
def detect_bos(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 10:
        return results

    highs = [c["high"] for c in candles[:-1]]
    lows = [c["low"] for c in candles[:-1]]
    curr = candles[-1]

    if curr["high"] > max(highs[-5:]):
        results.append(result("Break of Structure", tf, symbol, "High broke above previous 5-candle highs", 76, bias="bullish"))
    
    if curr["low"] < min(lows[-5:]):
        results.append(result("Break of Structure", tf, symbol, "Low broke below previous 5-candle lows", 76, bias="bearish"))

    return results

# --- Volume Spike Detection (vs avg) ---
def detect_volume_spike(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 21:
        return results

    volumes = [c["volume"] for c in candles[-21:-1]]
    avg_vol = statistics.mean(volumes)
    curr = candles[-1]

    if curr["volume"] > 1.8 * avg_vol:
        results.append(result("Volume Spike", tf, symbol, f"Volume surged to {curr['volume']:.2f}", 77, bias="neutral"))

    return results

def detect_order_block(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 3:
        return results

    for i in range(2, len(candles)):
        c1 = candles[i - 2]
        c2 = candles[i - 1]

        # Bullish OB: Red candle followed by large green engulfing
        if c1["close"] < c1["open"] and c2["close"] > c2["open"] and c2["close"] > c1["open"]:
            results.append(result("Bullish Order Block", tf, symbol, "Bullish OB formed via engulfing", 79, bias="bullish"))

        # Bearish OB: Green candle followed by large red engulfing
        if c1["close"] > c1["open"] and c2["close"] < c2["open"] and c2["close"] < c1["open"]:
            results.append(result("Bearish Order Block", tf, symbol, "Bearish OB formed via engulfing", 79, bias="bearish"))

    return results

def detect_liquidity_sweep(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    if len(candles) < 6:
        return results

    prev_highs = [c["high"] for c in candles[-6:-1]]
    prev_lows = [c["low"] for c in candles[-6:-1]]
    curr = candles[-1]

    # Bearish SFP: swept highs but closed lower
    if curr["high"] > max(prev_highs) and curr["close"] < max(prev_highs):
        results.append(result("Liquidity Sweep High (SFP)", tf, symbol, "Wick swept previous highs but closed below", 81, bias="bearish"))

    # Bullish SFP: swept lows but closed higher
    if curr["low"] < min(prev_lows) and curr["close"] > min(prev_lows):
        results.append(result("Liquidity Sweep Low (SFP)", tf, symbol, "Wick swept previous lows but closed above", 81, bias="bullish"))

    return results

# --- Helper (vs avg) ---
def group_patterns_by_bias(patterns: List[dict]) -> Dict[str, List[dict]]:
    grouped = {"bullish": [], "bearish": [], "neutral": []}
    for p in patterns:
        if p["bias"] in grouped:
            grouped[p["bias"]].append(p)
    return grouped


def detect_all_patterns(candles: List[dict], symbol: str, tf: str) -> List[dict]:
    results = []
    results += detect_fvg(candles, symbol, tf)
    results += detect_divergence(candles, symbol, tf)
    results += detect_bos(candles, symbol, tf)
    results += detect_volume_spike(candles, symbol, tf)
    results += detect_order_block(candles, symbol, tf)        
    results += detect_liquidity_sweep(candles, symbol, tf)     
    return results

