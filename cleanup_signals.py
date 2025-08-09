# close_signals.py
from datetime import datetime, timezone
from bson import ObjectId
from db import client as mongo_client
from market_data_ws import get_latest_ohlc

signals = mongo_client["hypewave"]["signals"]

def _ts_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def _decide_outcome(side: str, tp: float, sl: float, high: float, low: float) -> str | None:
    """
    Returns "win" if TP hit, "loss" if SL hit, or None if neither in this candle.
    If both hit in the same candle, assumes SL first (conservative).
    """
    side = (side or "").upper()
    if side == "LONG":
        hit_tp = high >= tp if tp else False
        hit_sl = low <= sl  if sl else False
    else:  # SHORT
        hit_tp = low <= tp  if tp else False
        hit_sl = high >= sl if sl else False

    if hit_tp and hit_sl:
        return "loss"   # tie-break: assume SL first (safer)
    if hit_tp:
        return "win"
    if hit_sl:
        return "loss"
    return None

def close_signals_once():
    """
    Scan OPEN signals and close them if TP/SL was hit (uses 5m candles window).
    Note: limited by how many candles market_data_ws caches (~last few hours).
    """
    open_cursor = signals.find({
        "$or": [{"status": "open"}, {"status": "OPEN"}],
        "output.tp": {"$exists": True},
        "output.sl": {"$exists": True},
        "input.symbol": {"$exists": True},
        "output.trade": {"$in": ["LONG", "SHORT"]}
    })

    for doc in open_cursor:
        sym = doc.get("input", {}).get("symbol")
        side = doc.get("output", {}).get("trade")
        tp = doc.get("output", {}).get("tp")
        sl = doc.get("output", {}).get("sl")
        created_at = doc.get("created_at")
        if not (sym and side and tp and sl and created_at):
            continue

        candles = get_latest_ohlc(f"{sym}USDT", "5m") or []
        if not candles:
            continue

        # Filter candles from (or after) creation time
        start_ms = _ts_ms(created_at)
        seq = [c for c in candles if int(c.get("timestamp", 0)) >= start_ms]
        if not seq:
            continue

        outcome = None
        hit_time = None
        hit_price = None
        hit_reason = None

        for c in seq:
            high = float(c["high"])
            low  = float(c["low"])
            when = int(c["timestamp"])

            res = _decide_outcome(side, float(tp), float(sl), high, low)
            if res:
                outcome = res
                hit_time = datetime.fromtimestamp(when / 1000, tz=timezone.utc)
                hit_reason = "tp" if res == "win" else "sl"
                hit_price = float(tp) if res == "win" else float(sl)
                break

        if outcome:
            signals.update_one(
                {"_id": ObjectId(doc["_id"]), "$or": [{"status": "open"}, {"status": "OPEN"}]},
                {"$set": {
                    "status": "closed",
                    "outcome": outcome,            # "win" | "loss"
                    "closed_at": datetime.now(timezone.utc),
                    "closed_reason": hit_reason,   # "tp" | "sl"
                    "hit_price": hit_price,
                    "hit_time": hit_time
                }}
            )
