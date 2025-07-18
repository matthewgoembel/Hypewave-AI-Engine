import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()

@router.get("/forex/calendar/today")
def get_economic_calendar():
    url = "https://www.investing.com/economic-calendar/"
    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table", {"id": "economicCalendarData"})
    if not table:
        return {"events": []}

    rows = table.find_all("tr", {"event_row": True})
    today = datetime.now(timezone.utc).strftime("%b %d")  # e.g., "Jul 18"
    events = []

    for row in rows:
        try:
            date = row.get("event_timestamp")
            if not date:
                continue

            time_cell = row.find("td", {"class": "time"})
            currency_cell = row.find("td", {"class": "left flagCur noWrap"})
            impact_cell = row.find("td", {"class": "sentiment"})
            event_cell = row.find("td", {"class": "event"})

            actual = row.find("td", {"class": "act"}).get_text(strip=True)
            forecast = row.find("td", {"class": "fore"}).get_text(strip=True)
            previous = row.find("td", {"class": "prev"}).get_text(strip=True)

            events.append({
                "date": datetime.fromtimestamp(int(date), tz=timezone.utc).strftime("%Y-%m-%d"),
                "time": time_cell.get_text(strip=True) if time_cell else "",
                "currency": currency_cell.get_text(strip=True) if currency_cell else "",
                "impact": len(impact_cell.find_all("i")) if impact_cell else 0,  # 1-3 impact level
                "detail": event_cell.get_text(strip=True) if event_cell else "",
                "actual": actual,
                "forecast": forecast,
                "previous": previous
            })
        except Exception as e:
            continue

    return {"events": events}
