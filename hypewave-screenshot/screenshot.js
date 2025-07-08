const puppeteer = require("puppeteer-extra");
const StealthPlugin = require("puppeteer-extra-plugin-stealth");
puppeteer.use(StealthPlugin());

async function scrapeTradingViewOverview(symbol = "ETH") {
  const url = `https://www.tradingview.com/symbols/${symbol}/`;

  const browser = await puppeteer.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-blink-features=AutomationControlled"
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  console.log(`🔍 Navigating to ${url}`);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });

  await page.waitForSelector('[data-symbol-price]');

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

const args = process.argv.slice(2);
scrapeTradingViewOverview(args[0] || "ETH").catch(err => {
  console.error("❌ ERROR:", err);
  process.exit(1);
});
