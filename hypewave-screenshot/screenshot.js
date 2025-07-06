const puppeteer = require("puppeteer");
const fs = require("fs");

async function screenshotTV(symbol = "BTCUSDT", tf = "15") {
  const url = `https://www.tradingview.com/chart/?symbol=BINANCE:${symbol}&interval=${tf}`;

  // 🟢 Launch Puppeteer without any executablePath
  // This makes it automatically use the bundled Chromium
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  console.log(`📸 Navigating to ${url}`);
  await page.goto(url, { waitUntil: "networkidle2" });
  await new Promise((resolve) => setTimeout(resolve, 3000)); // Let chart load

  // Save to /tmp/ (guaranteed writable)
  const tmpPath = `/tmp/${symbol}_${tf}.png`;
  await page.screenshot({ path: tmpPath });
  console.log(`✅ Saved screenshot to ${tmpPath}`);

  // Optional: Copy to media/
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
