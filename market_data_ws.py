# market_data_ws.py

import asyncio
import websockets
import json
from collections import defaultdict, deque

# Settings
CANDLE_STREAMS = {
    "BTCUSDT": ["5m", "15m", "1h", "4h"],
    "ETHUSDT": ["5m", "15m", "1h", "4h"],
    "SOLUSDT": ["5m", "15m", "1h", "4h"],
    "XAUUSDT": ["1m", "5m", "15m", "1h"]
}
MAX_CANDLES = 100  # Store last 100 candles for each symbol/timeframe

# Internal cache of candles
ohlc_data = defaultdict(lambda: defaultdict(lambda: deque(maxlen=MAX_CANDLES)))

# Build WebSocket URL
binance_socket = "wss://stream.binance.com:9443/stream?streams="
stream_urls = [f"{symbol.lower()}@kline_{interval}" for symbol, intervals in CANDLE_STREAMS.items() for interval in intervals]
ws_url = binance_socket + "/".join(stream_urls)

# --- WebSocket Candle Handler ---
def handle_kline(data):
    s = data.get("s")           # Symbol, e.g., BTCUSDT
    k = data.get("k", {})       # Kline data
    interval = k.get("i")       # Interval, e.g., "15m"

    if not all([s, interval, k.get("o"), k.get("h"), k.get("l"), k.get("c"), k.get("v"), k.get("t")]):
        return  # Incomplete data

    ohlc = {
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "timestamp": k["t"]
    }

    ohlc_data[s][interval].append(ohlc)

# --- WebSocket Listener ---
async def listen():
    print(f"🔌 Connecting to Binance WebSocket ({len(stream_urls)} streams)...")
    async with websockets.connect(ws_url) as ws:
        while True:
            msg = await ws.recv()
            try:
                payload = json.loads(msg)
                if payload.get("stream") and payload.get("data"):
                    handle_kline(payload["data"])
            except Exception as e:
                print(f"[WebSocket error] {e}")

# --- Signal Detection Loop (runs every 30s) ---
async def run_signal_detection():
    from signal_engine import generate_alerts_for_symbol  # ✅ Use the AI evaluation engine
    while True:
        print("🔁 Running signal evaluation cycle...")
        symbols_processed = set()
        for symbol in ohlc_data.keys():
            clean_symbol = symbol.replace("USDT", "").replace("USD", "").upper()
            if clean_symbol not in symbols_processed:
                print(f"[🧠 Sending {clean_symbol} to AI engine]")
                alerts = generate_alerts_for_symbol(clean_symbol)
                for alert in alerts:
                    print(f"✅ {alert}")
                symbols_processed.add(clean_symbol)
        await asyncio.sleep(30)

# --- Accessor for latest candles (optional) ---
def get_latest_ohlc(symbol: str, interval: str):
    return list(ohlc_data.get(symbol.upper(), {}).get(interval, []))

# --- Start everything in background ---
def start_ws_listener():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(listen())
    loop.create_task(run_signal_detection())

    print("📡 Binance WebSocket + AI Signal Engine started")
