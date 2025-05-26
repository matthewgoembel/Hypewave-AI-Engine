import requests
from fastapi import APIRouter

router = APIRouter()

# --- 1. BTC Price from CoinGecko ---
@router.get("/price")
def get_price(symbol: str = "bitcoin"):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        return {
            "symbol": symbol.upper(),
            "price_usd": data[symbol.lower()]["usd"]
        }
    except Exception as e:
        return {"error": str(e)}

# --- 2. Fear & Greed Index from Alternative.me ---
@router.get("/fear_greed")
def get_fear_greed():
    try:
        response = requests.get("https://api.alternative.me/fng/")
        data = response.json()["data"][0]
        return {
            "value": data["value"],
            "classification": data["value_classification"],
            "timestamp": data["timestamp"]
        }
    except Exception as e:
        return {"error": str(e)}

# --- 3. Funding Rate (Binance Futures) ---
@router.get("/funding")
def get_funding(symbol: str = "BTCUSDT"):
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol.upper()}&limit=1"
        response = requests.get(url)
        data = response.json()[0]
        return {
            "symbol": symbol.upper(),
            "fundingRate": float(data["fundingRate"]),
            "fundingTime": data["fundingTime"]
        }
    except Exception as e:
        return {"error": str(e)}

# --- 4. Global Long/Short Ratio (Binance Futures) ---
@router.get("/long_short")
def get_long_short_ratio(symbol: str = "BTCUSDT"):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol.upper()}&period=5m&limit=1"
        response = requests.get(url)
        data = response.json()[0]
        return {
            "symbol": symbol.upper(),
            "longAccountRatio": float(data["longAccountRatio"]),
            "shortAccountRatio": float(data["shortAccountRatio"]),
            "timestamp": data["timestamp"]
        }
    except Exception as e:
        return {"error": str(e)}
