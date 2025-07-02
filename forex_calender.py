import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

@router.get("/forex/calendar/today")
def get_forex_calendar():
    url = "https://www.forexfactory.com/calendar"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.select("tr.calendar__row")
    events = []

    today_str = datetime.now(timezone.utc).strftime("%a %b %-d").replace(" 0", " ")
    print("Today string:", today_str)

    current_date = None

    for row in rows:
        time_el = row.select_one("td.calendar__time")
        if not time_el or not time_el.text.strip():
            continue

        date_td = row.select_one("td.calendar__cell--date span.date")
        if date_td:
            parts = [s.strip() for s in date_td.strings if s.strip()]
            date_text = " ".join(parts)
        else:
            date_text = None

        if date_text:
            current_date = date_text

        print("Row current_date:", current_date)

        if current_date != today_str:
            continue

        currency = row.select_one("td.calendar__currency")
        impact_span = row.select_one("td.calendar__impact span")
        impact_level = (
            impact_span["class"][1].replace("icon--impact-", "").capitalize()
            if impact_span and len(impact_span["class"]) > 1
            else ""
        )
        detail = row.select_one("td.calendar__event")
        actual = row.select_one("td.calendar__actual")
        forecast = row.select_one("td.calendar__forecast")
        previous = row.select_one("td.calendar__previous")

        event = {
            "date": current_date,
            "time": time_el.text.strip(),
            "currency": currency.text.strip() if currency else "",
            "impact": impact_level,
            "detail": detail.text.strip() if detail else "",
            "actual": actual.text.strip() if actual else "",
            "forecast": forecast.text.strip() if forecast else "",
            "previous": previous.text.strip() if previous else "",
        }
        print("Event added:", event)
        events.append(event)

    print("Total events:", len(events))
    return {"events": events}