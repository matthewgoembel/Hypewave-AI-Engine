import requests

def extract_symbol(text: str) -> str:
    """
    Extracts a symbol like BTC, ETH from the text.
    Fallback to BTC.
    """
    import re
    match = re.search(r"\$([a-zA-Z]{2,10})", text)
    return match.group(1).upper() if match else "BTC"

def get_market_context(symbol: str = "BTC") -> str:
    """
    Returns a string summary with:
    - Last price
    - 24h change %
    - High / Low
    - Volume
    - Funding rate (if futures)
    - Long/Short ratio (if futures)
    """
    spot_symbol = f"{symbol}USDT"
    price = "N/A"
    change = "N/A"
    high = "N/A"
    low = "N/A"
    volume = "N/A"
    funding = "N/A"
    long_ratio = "N/A"
    short_ratio = "N/A"

    try:
        # 24h ticker
        ticker_res = requests.get(
            f"https://api.binance.com/api/v3/ticker/24hr?symbol={spot_symbol}",
            timeout=5
        )
        if ticker_res.ok:
            t = ticker_res.json()
            price = t.get("lastPrice", "N/A")
            change = t.get("priceChangePercent", "N/A")
            high = t.get("highPrice", "N/A")
            low = t.get("lowPrice", "N/A")
            volume = t.get("quoteVolume", "N/A")

        # Funding rate
        funding_res = requests.get(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={spot_symbol}&limit=1",
            timeout=5
        )
        if funding_res.ok:
            funding = float(funding_res.json()[0]["fundingRate"])

        # Long/Short ratio
        ls_res = requests.get(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={spot_symbol}&period=5m&limit=1",
            timeout=5
        )
        if ls_res.ok:
            ls = ls_res.json()[0]
            long_ratio = float(ls["longAccountRatio"])
            short_ratio = float(ls["shortAccountRatio"])

    except Exception as e:
        return f"**Market Context Unavailable**\nError: {str(e)}"

    context = f"""
<b>Live Market Context for ${symbol}</b><br>
• Price: ${price}<br>
• 24h Change: {change}%<br>
• High: ${high} / Low: ${low}<br>
• Volume (24h): ${volume}<br>
• Funding Rate: {funding if funding != 'N/A' else 'N/A'}<br>
• Long/Short Ratio: {long_ratio if long_ratio != 'N/A' else 'N/A'} Long / {short_ratio if short_ratio != 'N/A' else 'N/A'} Short
""".strip()

    return context
