"""
truth_social_scraper.py
------------------------

Fetches President Trump's Truth Social posts
and stores them in MongoDB (truthsocial_news collection).

✅ Features:
- Uses Playwright to render dynamic JavaScript content.
- Skips duplicate posts.
- Stores timestamp, text, and post link.
- Ready to run in a background loop.

"""

import os
import asyncio
from datetime import datetime, timezone
from pymongo import MongoClient
from playwright.async_api import async_playwright

# Load MongoDB connection from environment
client = MongoClient(os.getenv("MONGO_DB_URI"))
collection = client["hypewave"]["truth_social"]

async def fetch_truthsocial():
    """
    Fetches the latest posts from Trump's Truth Social feed.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Load Trump's profile
        await page.goto("https://truthsocial.com/@realDonaldTrump")
        await page.wait_for_timeout(5000)  # Wait for dynamic content

        # Extract posts with JavaScript
        posts = await page.evaluate("""
        () => {
            const elements = document.querySelectorAll("div[data-testid='post-container']");
            return Array.from(elements).map(el => {
                const textEl = el.querySelector("div[dir='auto']");
                const timeEl = el.querySelector("time");
                const text = textEl ? textEl.innerText : "";
                const timestamp = timeEl ? timeEl.getAttribute("datetime") : "";
                const id = timeEl ? timeEl.parentElement.getAttribute("href").split("/").pop() : "";
                return {id, text, timestamp};
            });
        }
        """)

        new_count = 0
        for post in posts:
            if not post["id"] or not post["text"]:
                continue

            # Convert timestamp to datetime object
            dt = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))

            # Skip duplicates
            if collection.find_one({"id": post["id"]}):
                continue

            # Insert new post
            doc = {
                "id": post["id"],
                "text": post["text"],
                "date": dt,
                "link": f"https://truthsocial.com/@realDonaldTrump/posts/{post['id']}",
                "source": "realDonaldTrump",
                "display_name": "Donald J. Trump",
                "media_url": None
            }
            collection.insert_one(doc)
            new_count += 1
            print(f"[TruthSocial] Added: {post['text'][:60]}...")

        await browser.close()
        print(f"[TruthSocial] Fetched {len(posts)} posts, {new_count} new.")

async def loop_fetch():
    """
    Runs fetch_truthsocial() every minute.
    """
    while True:
        try:
            await fetch_truthsocial()
        except Exception as e:
            print(f"[TruthSocial Error]: {e}")
        await asyncio.sleep(60)  # Fetch every 60 seconds

if __name__ == "__main__":
    asyncio.run(loop_fetch())
