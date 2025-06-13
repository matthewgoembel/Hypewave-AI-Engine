import requests
import re

def extract_symbol(text: str) -> str:
    match = re.search(r"\$([a-zA-Z]{2,10})", text)
    return match.group(1).upper() if match else "BTC"

def get_market_context(symbol: str = "BTC") -> str:
    try:
        price = "N/A"
        funding = "N/A"
        long_ratio = "N/A"
        short_ratio = "N/A"
        fng_value = "N/A"
        fng_classification = "N/A"

        # Try CoinGecko for crypto price
        cg_res = requests.get(f"https://api.coingecko.com/api/v3/coins/list")
        coins = cg_res.json()
        coin_id = next((c['id'] for c in coins if c['symbol'].upper() == symbol.upper()), None)

        if coin_id:
            price_res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd")
            price = price_res.json().get(coin_id, {}).get("usd", "N/A")

            # Try Binance-specific funding and ratio if it's a common pair
            try:
                funding_res = requests.get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}USDT&limit=1")
                funding = float(funding_res.json()[0]["fundingRate"])

                ls_res = requests.get(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}USDT&period=5m&limit=1")
                ls = ls_res.json()[0]
                long_ratio = float(ls["longAccountRatio"])
                short_ratio = float(ls["shortAccountRatio"])
            except:
                pass

        if symbol.upper() == "BTC":
            fng_res = requests.get("https://api.alternative.me/fng/")
            fng = fng_res.json()["data"][0]
            fng_value = fng["value"]
            fng_classification = fng["value_classification"]

        context = f"""
**Live Market Context for {symbol.upper()}**

- **Price:** ${price}
- **Fear & Greed Index:** {fng_value} ({fng_classification})
- **Funding Rate:** {funding if funding != 'N/A' else 'N/A'}
- **Long/Short Ratio:** {long_ratio if long_ratio != 'N/A' else 'N/A'} Long / {short_ratio if short_ratio != 'N/A' else 'N/A'} Short
"""
        return context.strip()

    except Exception as e:
        return f"**Market Context Unavailable**\nError: {str(e)}"
