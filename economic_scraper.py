# economic_scraper.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
import os
import dotenv

dotenv.load_dotenv()
MONGO_URI = os.getenv("MONGO_DB_URI")

def scrape_marketwatch_calendar():
    url = "https://www.marketwatch.com/economy-politics/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        raise Exception(f"Failed to fetch page. Status code: {res.status_code}")

    soup = BeautifulSoup(res.text, "html.parser")
    tables = soup.select("div.element.element--tableblock table")

    if not tables:
        raise Exception("Could not find any calendar tables.")

    output = []

    for idx, table in enumerate(tables, 1):
        label = {
            1: "📆 This Week",
            2: "🔮 Next Week",
            3: "📆 Last Week"
        }.get(idx, f"Table #{idx}")

        section = {"section": label, "events": []}
        rows = table.find_all("tr")
        current_day_label = None

        for row in rows:
            tds = row.find_all("td")
            if len(tds) == 1:
                current_day_label = tds[0].get_text(strip=True)
                section["events"].append({
                    "date_label": current_day_label,
                    "events": []
                })
            elif len(tds) >= 6:
                time = tds[0].get_text(strip=True)
                title_tag = tds[1].find("a")
                title = title_tag.get_text(strip=True) if title_tag else tds[1].get_text(strip=True)
                period = tds[2].get_text(strip=True)
                actual = tds[3].get_text(strip=True)
                forecast = tds[4].get_text(strip=True)
                previous = tds[5].get_text(strip=True)

                if not section["events"]:
                    section["events"].append({"date_label": "Unlabeled", "events": []})

                section["events"][-1]["events"].append({
                    "time": time,
                    "title": title,
                    "period": period,
                    "actual": actual,
                    "forecast": forecast,
                    "previous": previous
                })

        output.append(section)

    return output


if __name__ == "__main__":
    calendar = scrape_marketwatch_calendar()

    # Calculate start of this week (Monday)
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    week_of = monday.date().isoformat()

    # Push to MongoDB
    client = MongoClient(MONGO_URI)
    calendar_coll = client["hypewave"]["calendar_cache"]
    calendar_coll.insert_one({
        "week_of": week_of,
        "calendar": calendar,
        "scraped_at": now
    })

    print(f"✅ Scraped and stored calendar for week of {week_of}")
