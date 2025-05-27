# alert_engine.py

import time
import requests
from urllib.parse import quote
from db import client, log_alert

# MongoDB collection holding user watchlists
watchlist_collection = client["hypewave"]["watchlists"]

# In-memory store of last alerts per (user, symbol)
_last_alerts: dict[tuple[str,str], set[str]] = {}

# Cache CoinGecko symbol→id map on import
def _load_cg_map():
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=10)
        coins = resp.json()
        return {c["symbol"].upper(): c["id"] for c in coins}
    except Exception:
        return {}
_CG_SYMBOL_TO_ID = _load_cg_map()

def fetch_market_data(symbol: str) -> dict:
    symbol = symbol.upper()
    data: dict = {}

    # 1) Crypto via CoinGecko (price + 24h volume)
    cg_id = _CG_SYMBOL_TO_ID.get(symbol)
    if cg_id:
        try:
            url = (
                f"https://api.coingecko.com/api/v3/simple/price"
                f"?ids={cg_id}&vs_currencies=usd&include_24hr_vol=true"
            )
            j = requests.get(url, timeout=5).json()[cg_id]
            data["price"]  = j.get("usd", 0)
            data["volume"] = j.get("usd_24h_vol", 0)
        except Exception:
            pass

    # 2) Fallback to Yahoo Finance (for stocks/commodities)
    if "price" not in data:
        try:
            yf_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote(symbol)}"
            r = requests.get(yf_url, timeout=5).json()
            res = r.get("quoteResponse", {}).get("result", [])
            if res:
                q = res[0]
                data["price"]  = q.get("regularMarketPrice", 0)
                data["volume"] = q.get("regularMarketVolume", 0)
        except Exception:
            pass

    # 3) Binance futures for funding & L/S ratio (crypto only)
    try:
        fr = requests.get(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}USDT&limit=1",
            timeout=5
        ).json()
        data["funding_rate"] = float(fr[0]["fundingRate"])
    except Exception:
        data["funding_rate"] = 0.0

    try:
        ls = requests.get(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            f"?symbol={symbol}USDT&period=5m&limit=1",
            timeout=5
        ).json()
        data["long_short_ratio"] = float(ls[0]["longAccountRatio"])
    except Exception:
        data["long_short_ratio"] = 0.0

    # 4) Stub structural flags → default to False
    data["support_zone"]    = data.get("price", 0) * 0.98
    data["resistance_zone"] = data.get("price", 0) * 1.02
    data["divergence"]      = False
    data["fvg"]             = False
    data["liquidity_sweep"] = False

    return data

def generate_alerts_for_user(symbol: str, user_id: str) -> list[str]:
    data = fetch_market_data(symbol)
    alerts: list[str] = []
    key = (user_id, symbol)

    # Skip if we couldn't get a price
    if data.get("price", 0) == 0:
        return []

    # 1) Volume spike
    if data["volume"] > 1e7:
        alerts.append(f"{symbol}: High volume spike ({int(data['volume']):,})")

    # 2) Liquidity sweep (once you implement real logic, remove the stub)
    if data["liquidity_sweep"]:
        alerts.append(f"{symbol}: Liquidity sweep at key levels—check for reversal")

    # 3) Fair Value Gap
    if data["fvg"]:
        alerts.append(f"{symbol}: Fair Value Gap detected—potential magnet zone")

    # 4) Divergence
    if data["divergence"]:
        alerts.append(f"{symbol}: Momentum divergence detected")

    # 5) Funding rate extremes
    if abs(data["funding_rate"]) > 0.05:
        alerts.append(f"{symbol}: Funding rate at {data['funding_rate']:.2%}—crowded positioning")

    # Deduplicate: only keep alerts we haven't sent yet
    seen = _last_alerts.setdefault(key, set())
    new_alerts = [a for a in alerts if a not in seen]
    seen.update(new_alerts)

    # Log new alerts into MongoDB
    for text in new_alerts:
        log_alert(user_id, {"symbol": symbol}, {"result": text, "source": "auto-alert"})

    return new_alerts

def run_alert_loop():
    print("🟢 Starting alert loop (every 10s)…")
    while True:
        for wl in watchlist_collection.find():
            user_id = wl.get("user_id", "unknown")
            for symbol in wl.get("symbols", []):
                for alert in generate_alerts_for_user(symbol, user_id):
                    print(f"[{user_id}][{symbol}] {alert}")
        time.sleep(10)

if __name__ == "__main__":
    run_alert_loop()
