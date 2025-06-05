import requests

# Basic REST OHLC fetch for BTC

def test_binance_rest(symbol="BTCUSDT", interval="1h"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        ohlc = response.json()[0]
        data = {
            "open": ohlc[1],
            "high": ohlc[2],
            "low": ohlc[3],
            "close": ohlc[4],
            "volume": ohlc[5]
        }
        print(f"✅ Live OHLC for {symbol} ({interval}):")
        for k, v in data.items():
            print(f"- {k.title()}: {v}")
    except Exception as e:
        print(f"❌ Error connecting to Binance API: {e}")


if __name__ == "__main__":
    test_binance_rest()
