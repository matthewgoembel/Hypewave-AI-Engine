from fastapi import APIRouter
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

router = APIRouter()

@router.get("/forex/calendar/today")
def get_forex_calendar():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.forexfactory.com/calendar")
        page.wait_for_selector("tr.calendar__row", timeout=15000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    rows = soup.select("tr.calendar__row")
    events = []

    today_str = datetime.now(timezone.utc).strftime("%a %b %-d").replace(" 0", " ")
    print("Today string:", today_str)

    current_date = None

    for row in rows:
        print("======== NEW ROW ==========")

        time_el = row.select_one("td.calendar__time")
        time_text = time_el.text.strip() if time_el else ""
        print("Time text:", repr(time_text))

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

        if not current_date:
            print("Skipping row because no current_date.")
            continue

        if current_date != today_str:
            print(f"Skipping because '{current_date}' != '{today_str}'")
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
            "time": time_text,
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
