"""
truth_social_scraper.py
------------------------

Fetches the single most recent Truth Social post and stores it in MongoDB, including images.

✅ Features:
- Uses Playwright to render JavaScript.
- Fetches only the most recent post.
- Extracts text, timestamp, link, and image URLs.
- Skips duplicates.
"""

import os
import asyncio
from datetime import datetime, timezone
from pymongo import MongoClient
from playwright.async_api import async_playwright

client = MongoClient(os.getenv("MONGO_DB_URI"))
collection = client["hypewave"]["truth_social"]

async def fetch_latest_truthsocial():
    """
    Fetches the latest (most recent) post from Trump's Truth Social feed.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://truthsocial.com/@realDonaldTrump")
        await page.wait_for_selector("div[data-testid='status']")

        # Extract only the first post with images
        post = await page.evaluate("""
        () => {
            const el = document.querySelector("div[data-testid='status']");
            if (!el) return null;
            const textEl = el.querySelector("p");
            const timeEl = el.querySelector("time");
            const linkEl = el.querySelector("a[role='link']");
            const imageEls = el.querySelectorAll("img");
            const text = textEl ? textEl.innerText : "";
            const timestamp = timeEl ? timeEl.getAttribute("datetime") : "";
            const href = linkEl ? linkEl.getAttribute("href") : "";
            const id = href ? href.split("/").pop() : "";
            const images = Array.from(imageEls).map(img => img.getAttribute("src"));
            return {id, text, timestamp, images};
        }
        """)

        if not post or not post["id"] or not post["text"]:
            print("[TruthSocial] No valid post found.")
            await browser.close()
            return

        if collection.find_one({"id": post["id"]}):
            print("[TruthSocial] No new post.")
            await browser.close()
            return

        dt = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))

        doc = {
            "id": post["id"],
            "text": post["text"],
            "timestamp": dt.isoformat(),
            "link": f"https://truthsocial.com/@realDonaldTrump/posts/{post['id']}",
            "source": "realDonaldTrump",
            "display_name": "Donald J. Trump",
            "media_urls": post["images"] or []
        }
        collection.insert_one(doc)
        print(f"[TruthSocial] NEW POST: {post['text'][:60]}... Images: {len(post['images'])}")

        # You could trigger your frontend update here

        await browser.close()

async def loop_fetch():
    """
    Runs fetch_latest_truthsocial() every 30 seconds.
    """
    while True:
        try:
            await fetch_latest_truthsocial()
        except Exception as e:
            print(f"[TruthSocial Error]: {e}")
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
