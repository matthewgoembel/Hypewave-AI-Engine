const puppeteer = require("puppeteer");

async function scrapeTradingViewSymbol(symbol = "BTCUSD") {
  const url = `https://www.tradingview.com/symbols/${symbol}/technicals/`;

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  console.log(`🔍 Navigating to ${url}`);
  await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });

  // Wait for the summary rating
  await page.waitForSelector('[data-widget-type="summary"]');

  const data = await page.evaluate(() => {
    const summaryEl = document.querySelector('[data-widget-type="summary"]');
    const rating = summaryEl?.querySelector('.speedometerSignal-pyzN--tL')?.innerText.trim();

    // Optionally extract moving averages (if visible)
    const movingAverages = {};
    document.querySelectorAll('div.indicatorValue-LH4ML9CP').forEach((el, i) => {
      movingAverages[`MA${i+1}`] = el.innerText.trim();
    });

    return {
      rating: rating || "N/A",
      movingAverages,
    };
  });

  console.log("✅ Extracted Data:", data);

  await browser.close();
  return data;
}

// Accept CLI args
const args = process.argv.slice(2);
scrapeTradingViewSymbol(args[0] || "BTCUSD").catch(err => {
  console.error("❌ ERROR:", err);
  process.exit(1);
});
