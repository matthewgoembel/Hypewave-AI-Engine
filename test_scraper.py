import requests
from bs4 import BeautifulSoup

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

    print("[*] Sending request...")
    res = requests.get(url, headers=headers)
    print(f"[*] Status Code: {res.status_code}")

    if res.status_code != 200:
        print("[-] Failed to fetch page.")
        return

    print("[*] Parsing HTML...")
    soup = BeautifulSoup(res.text, "html.parser")

    # More accurate selector based on your provided HTML
    tables = soup.select("div.element.element--tableblock table")
    if not tables:
        print("[-] Could not find any calendar tables.")
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        return

    print(f"[+] Found {len(tables)} calendar tables.\n")
    output = []

    for idx, table in enumerate(tables, 1):
        label = {
            1: "📆 This Week",
            2: "🔮 Next Week",
            3: "📆 Last Week"
        }.get(idx, f"Table #{idx}")
        output.append(f"\n===== {label} =====\n")

        rows = table.find_all("tr")
        current_day_header = ""

        for row in rows:
            tds = row.find_all("td")
            if len(tds) == 1:
                current_day_header = tds[0].get_text(strip=True)
                output.append(f"[ at **{current_day_header}**]")
            elif len(tds) >= 6:
                time = tds[0].get_text(strip=True)
                title_tag = tds[1].find("a")
                title = title_tag.get_text(strip=True) if title_tag else tds[1].get_text(strip=True)
                period = tds[2].get_text(strip=True)
                actual = tds[3].get_text(strip=True)
                forecast = tds[4].get_text(strip=True)
                previous = tds[5].get_text(strip=True)

                output.append(f"[{period} at {time}] {title}")
                output.append(f"   Actual: {actual} | Forecast: {forecast} | Previous: {previous}\n")

    print("\n".join(output))


if __name__ == "__main__":
    scrape_marketwatch_calendar()
