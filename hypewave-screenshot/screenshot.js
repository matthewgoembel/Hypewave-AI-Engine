const puppeteer = require("puppeteer");

async function screenshotTV(symbol = "BTCUSDT", tf = "15") {
  const url = `https://www.tradingview.com/chart/?symbol=BINANCE:${symbol}&interval=${tf}`;
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  await page.goto(url, { waitUntil: "networkidle2" });

  // Use native wait instead of waitForTimeout
  await new Promise(resolve => setTimeout(resolve, 3000));

  const filename = `../media/${symbol}_${tf}.png`; // go up a level if media is outside
  await page.screenshot({ path: filename });
  await browser.close();

  console.log(`✅ Screenshot saved: ${filename}`);
}

// Accept CLI args: node screenshot.js BTCUSDT 15
const args = process.argv.slice(2);
screenshotTV(args[0] || "BTCUSDT", args[1] || "15");
