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

    # Today in the site format, e.g., "Wed Jul 2"
    today_str = datetime.now(timezone.utc).strftime("%a %b %-d").replace(" 0", " ")
    print("Today string:", today_str)

    current_date = None

    for row in rows:
        print("======== NEW ROW ==========")

        time_el = row.select_one("td.calendar__time")
        if not time_el or not time_el.text.strip():
            print("Skipping row with no time.")
            continue

        # Extract and normalize date
        date_td = row.select_one("td.calendar__cell--date span.date")
        if date_td:
            parts = [s.strip() for s in date_td.strings if s.strip()]
            print("Date parts raw:", parts)
            date_text = " ".join(" ".join(parts).split())
            print("Computed date_text:", date_text)
        else:
            date_text = None

        if date_text:
            current_date = date_text

        print("Final current_date in row:", current_date)
        print("Time:", time_el.text.strip())

        # Log and skip if date doesn't match
        if current_date != today_str:
            print(f"Skipping because '{current_date}' != '{today_str}'")
            continue

        # Extract other fields
        currency = row.select_one("td.calendar__currency")
        impact_span = row.select_one("td.calendar__impact span")
        # Handle impact from class name
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
