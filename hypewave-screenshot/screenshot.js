const puppeteer = require("puppeteer");

async function scrapeTradingViewOverview(symbol = "XAUUSD") {
  const url = `https://www.tradingview.com/symbols/${symbol}/`;

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  console.log(`🔍 Navigating to ${url}`);
  await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });

  // Wait for the price element
  await page.waitForSelector('[data-symbol-price]');

  // Extract data
  const data = await page.evaluate(() => {
    const priceEl = document.querySelector('[data-symbol-price]');
    const changeEl = document.querySelector('[data-symbol-change]');
    const titleEl = document.querySelector("h1") || {};

    return {
      name: titleEl.innerText || "N/A",
      price: priceEl ? priceEl.innerText.trim() : "N/A",
      change: changeEl ? changeEl.innerText.trim() : "N/A",
    };
  });

  console.log("✅ Extracted Data:", data);

  await browser.close();
  return data;
}

// Accept CLI args
const args = process.argv.slice(2);
scrapeTradingViewOverview(args[0] || "XAUUSD").catch(err => {
  console.error("❌ ERROR:", err);
  process.exit(1);
});
