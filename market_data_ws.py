# market_data_ws.py

import asyncio
import websockets
import json
from collections import defaultdict

CANDLE_STREAMS = {
    "BTCUSDT": ["15m", "1h", "4h"],
    "ETHUSDT": ["15m", "1h", "4h"],
    "SPXUSDT": ["5m", "15m", "1h"],
    "XAUUSDT": ["5m", "15m", "1h"]
}

binance_socket = "wss://stream.binance.com:9443/stream?streams="

# Build combined stream URL for all symbols/timeframes
stream_urls = []
for symbol, intervals in CANDLE_STREAMS.items():
    for interval in intervals:
        stream_urls.append(f"{symbol.lower()}@kline_{interval}")

ws_url = binance_socket + "/".join(stream_urls)

# Internal cache of candles
ohlc_data = defaultdict(dict)

# Callback: handle new candles
def handle_kline(data):
    s = data.get("s")
    k = data.get("k", {})
    if not all([s, k.get("i"), k.get("o"), k.get("h"), k.get("l"), k.get("c"), k.get("v"), k.get("t")]):
        return

    interval = k["i"]
    ohlc = {
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "timestamp": k["t"]
    }
    ohlc_data[s][interval] = ohlc

# Public accessor to get latest OHLC
def get_latest_ohlc(symbol: str, interval: str):
    return ohlc_data.get(symbol.upper(), {}).get(interval, {})

# Main loop
async def listen():
    print(f"🔌 Connecting to Binance WebSocket for {len(stream_urls)} streams...")
    async with websockets.connect(ws_url) as ws:
        while True:
            msg = await ws.recv()
            try:
                payload = json.loads(msg)
                if payload.get("stream") and payload.get("data"):
                    handle_kline(payload["data"])
            except Exception as e:
                print(f"[WebSocket error] {e}")

# To run in background
def start_ws_listener():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(listen())
    print("📡 Binance WebSocket streaming started")
