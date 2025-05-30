import os, time, sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from tweepy import Client, TweepyException
from db import client as mongo_client

# ——— Configuration ———
TWITTER_BEARER = os.getenv("TWITTER_BEARER_TOKEN")
if not TWITTER_BEARER:
    raise RuntimeError("Set TWITTER_BEARER_TOKEN in your .env")

POLL_INTERVAL = 1800  # 30 minutes
STARTUP_TIME = datetime.now(timezone.utc)

ACCOUNTS = ["hypewave_ai"]  # #, "WatcherGuru", "nypost"
    # Add more later
    #, "aeyakovenko", "cz_binance"
    #"thelordofentry", "Bloomberg", "Reuters", "CoinDesk", "intocryptoverse",
    #"WSJ", "degeneratenews", "elonmusk",

# ——— Setup ———
twitter = Client(bearer_token=TWITTER_BEARER, wait_on_rate_limit=True)
db = mongo_client["hypewave"]
tweets_coll = db["tweets"]
users_coll = db["users"]

_user_ids: Dict[str, str] = {}
_last_seen: Dict[str, str] = {}

# ——— Load or Cache User ID Once ———
def init_user_ids():
    print("🔁 Loading user IDs from MongoDB...")
    for username in ACCOUNTS:
        cached = users_coll.find_one({"username": username})
        if cached:
            _user_ids[username] = cached["id"]
        else:
            while True:
                try:
                    resp = twitter.get_user(username=username, user_fields=["id", "username"])
                    if resp and resp.data:
                        uid = resp.data.id
                        _user_ids[username] = uid
                        users_coll.insert_one({"username": username, "id": uid})
                        print(f"✅ Cached @{username} → {uid}")
                        break
                except TweepyException as e:
                    print(f"[Error] Cannot fetch @{username}: {e}")
                    print("⏳ Sleeping 300s before retrying...")
                    time.sleep(300)

# ——— Fetch New Tweets ———
def fetch_new_for_user(handle: str, max_results: int = 5) -> List:
    uid = _user_ids.get(handle)
    if not uid:
        return []

    since_id: Optional[str] = _last_seen.get(handle)
    try:
        resp = twitter.get_users_tweets(
            id=uid,
            since_id=since_id,
            max_results=max_results,
            tweet_fields=["id", "text", "created_at", "author_id"]
        )
    except TweepyException as e:
        print(f"[Error] get_users_tweets for @{handle}: {e}")
        return []

    tweets = resp.data or []
    filtered = [t for t in tweets if t.created_at and t.created_at > STARTUP_TIME]
    if filtered:
        _last_seen[handle] = str(filtered[0].id)

    return filtered

# ——— Save to MongoDB ———
def save_tweets(source: str, tweets: List) -> None:
    for tw in tweets:
        tweets_coll.update_one(
            {"tweet_id": tw.id},
            {"$set": {
                "tweet_id":   tw.id,
                "user":       source,
                "content":    tw.text,
                "created_at": tw.created_at.isoformat()
            }},
            upsert=True
        )

# ——— Main Loop ———
def run_loop(interval_seconds: int = POLL_INTERVAL) -> None:
    init_user_ids()
    print(f"🟢 Twitter fetcher started — checking @{ACCOUNTS[0]} every {interval_seconds // 60} minutes")

    while True:
        handle = ACCOUNTS[0]
        tweets = fetch_new_for_user(handle)
        if tweets:
            save_tweets(handle, tweets)
            print(f"  • @{handle}: saved {len(tweets)} new tweets")
        else:
            print(f"  • @{handle}: no new tweets")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    run_loop()

def run_once_now():
    init_user_ids()
    handle = ACCOUNTS[0]
    print(f"⚡ Manual fetch for @{handle}...")
    tweets = fetch_new_for_user(handle)
    if tweets:
        save_tweets(handle, tweets)
        print(f"  • @{handle}: saved {len(tweets)} new tweets")
    else:
        print(f"  • @{handle}: no new tweets")

if __name__ == "__main__":
    if "--now" in sys.argv:
        run_once_now()
    else:
        run_loop()