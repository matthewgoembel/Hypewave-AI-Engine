import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/forex/calendar/today")
def get_forex_calendar():
    url = "https://www.forexfactory.com/calendar"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")


    rows = soup.select("tr.calendar__row")
    events = []
    today_str = datetime.utcnow().strftime("%b %d")  # E.g., "Jul 02"

    for row in rows:
        # Some rows are empty separators
        if not row.select_one("td.time"):
            continue

        # Extract cells
        date_el = row.select_one("td.date")
        time_el = row.select_one("td.time")
        currency = row.select_one("td.currency")
        impact = row.select_one("td.impact span")
        detail = row.select_one("td.event")
        actual = row.select_one("td.actual")
        forecast = row.select_one("td.forecast")
        previous = row.select_one("td.previous")

        date_text = date_el.text.strip() if date_el else today_str
        time_text = time_el.text.strip()

        events.append({
            "date": date_text,
            "time": time_text,
            "currency": currency.text.strip() if currency else "",
            "impact": impact["title"] if impact and impact.has_attr("title") else "",
            "detail": detail.text.strip() if detail else "",
            "actual": actual.text.strip() if actual else "",
            "forecast": forecast.text.strip() if forecast else "",
            "previous": previous.text.strip() if previous else "",
        })

    return {"events": events}
