# alert_engine.py

import time
import logging
from typing import Dict, List, Set, Tuple
from urllib.parse import quote

import requests
from db import client, log_alert

# Set up module-level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# MongoDB collection holding user watchlists
watchlist_collection = client["hypewave"]["watchlists"]

# In-memory store of which alerts have already gone out per (user, symbol)
_last_alerts: Dict[Tuple[str, str], Set[str]] = {}

# Cache CoinGecko symbol→id map on import
def _load_cg_map() -> Dict[str, str]:
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=10)
        coins = resp.json()
        return {c["symbol"].upper(): c["id"] for c in coins}
    except Exception as e:
        logger.warning(f"Failed to load CoinGecko list: {e}")
        return {}

_CG_SYMBOL_TO_ID = _load_cg_map()

def fetch_market_data(symbol: str) -> Dict:
    """Fetch price, volume, funding & L/S ratio, plus stubbed structural data."""
    symbol = symbol.upper()
    data: Dict = {}

    # 1) Crypto via CoinGecko
    cg_id = _CG_SYMBOL_TO_ID.get(symbol)
    if cg_id:
        try:
            url = (
                f"https://api.coingecko.com/api/v3/simple/price"
                f"?ids={cg_id}&vs_currencies=usd&include_24hr_vol=true"
            )
            j = requests.get(url, timeout=5).json()[cg_id]
            data["price"]  = j.get("usd", 0.0)
            data["volume"] = j.get("usd_24h_vol", 0.0)
        except Exception as e:
            logger.debug(f"CoinGecko fetch failed for {symbol}: {e}")

    # 2) Fallback Yahoo Finance
    if "price" not in data or data["price"] == 0:
        try:
            yf_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote(symbol)}"
            r = requests.get(yf_url, timeout=5).json()
            res = r.get("quoteResponse", {}).get("result", [])
            if res:
                q = res[0]
                data["price"]  = q.get("regularMarketPrice", 0.0)
                data["volume"] = q.get("regularMarketVolume", 0.0)
        except Exception as e:
            logger.debug(f"Yahoo Finance fetch failed for {symbol}: {e}")

    # 3) Binance futures for funding & L/S ratio
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

    # 4) Stub structural metrics
    data["support_zone"]    = data.get("price", 0.0) * 0.98
    data["resistance_zone"] = data.get("price", 0.0) * 1.02
    data["divergence"]      = detect_divergence(symbol, data)
    data["fvg"]             = detect_fvg(symbol, data)
    data["liquidity_sweep"] = detect_liquidity_sweep(symbol, data)

    return data

def detect_divergence(symbol: str, data: Dict) -> bool:
    """Stub: replace with your real divergence logic."""
    return False

def detect_fvg(symbol: str, data: Dict) -> bool:
    """Stub: replace with your real Fair Value Gap logic."""
    return False

def detect_liquidity_sweep(symbol: str, data: Dict) -> bool:
    """Stub: replace with your real liquidity sweep logic."""
    return False

def generate_alert(symbol: str, user_id: str) -> List[str]:
    """
    Build new alerts for (user_id, symbol), dedupe against
    alerts already sent (_last_alerts), log to Mongo, and return them.
    """
    data = fetch_market_data(symbol)
    alerts: List[str] = []
    key = (user_id, symbol)

    # No price → skip entirely
    if data.get("price", 0.0) <= 0:
        return []

    # 1) Volume spike
    if data["volume"] > 1e7:
        alerts.append(f"{symbol}: High volume spike ({int(data['volume']):,})")

    # 2) Liquidity sweep
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
        fr_pct = data["funding_rate"] * 100
        alerts.append(f"{symbol}: Funding rate at {fr_pct:.2f}%—crowded positioning")

    # Dedupe & log only new alerts
    seen = _last_alerts.setdefault(key, set())
    new_alerts = [a for a in alerts if a not in seen]
    seen.update(new_alerts)

    for text in new_alerts:
        log_alert(user_id, {"symbol": symbol}, {"result": text, "source": "auto-alert"})
        logger.info(f"Logged alert for {user_id}-{symbol}: {text}")

    return new_alerts

def run_alert_loop(interval: float = 10.0) -> None:
    """Continuously scan each user’s watchlist every `interval` seconds."""
    logger.info(f"🟢 Starting alert loop (every {interval}s)…")
    while True:
        try:
            for wl in watchlist_collection.find():
                user_id = wl.get("user_id", "unknown")
                symbols = wl.get("symbols", [])
                for sym in symbols:
                    for alert in generate_alert(sym.upper(), user_id):
                        print(f"[{user_id}][{sym}] {alert}")
        except Exception as e:
            logger.error(f"Alert loop error: {e}", exc_info=True)
        time.sleep(interval)

if __name__ == "__main__":
    run_alert_loop()
