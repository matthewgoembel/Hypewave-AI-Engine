const puppeteer = require("puppeteer");
const fs = require("fs");

async function screenshotTV(symbol = "BTCUSDT", tf = "15") {
  const url = `https://www.binance.us/spot-trade/${symbol.toLowerCase()}`;

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  // 🟢 Block images, fonts, stylesheets
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    const resourceType = request.resourceType();
    if (["image", "stylesheet", "font"].includes(resourceType)) {
      request.abort();
    } else {
      request.continue();
    }
  });

  console.log(`📸 Navigating to ${url}`);
  await page.goto(url, { waitUntil: "networkidle2", timeout: 90000 });

  // 🟢 Wait for the chart container to be visible
  await page.waitForSelector(".kline-container", { timeout: 20000 });

  await new Promise((resolve) => setTimeout(resolve, 3000)); // Let chart render

  // Save to /tmp/
  const tmpPath = `/tmp/${symbol}_${tf}.png`;
  await page.screenshot({ path: tmpPath });
  console.log(`✅ Saved screenshot to ${tmpPath}`);

  // Copy to media/
  const mediaPath = `../media/${symbol}_${tf}.png`;
  if (!fs.existsSync("../media")) {
    fs.mkdirSync("../media");
  }
  fs.copyFileSync(tmpPath, mediaPath);
  console.log(`📁 Copied screenshot to ${mediaPath}`);

  await browser.close();
}

// Accept CLI args
const args = process.argv.slice(2);
screenshotTV(args[0] || "BTCUSDT", args[1] || "15");

// Show errors
process.on("unhandledRejection", (err) => {
  console.error("❌ UNHANDLED ERROR:", err);
  process.exit(1);
});
