// Capture TradeSense pages with Playwright chromium (stable waits, no blank shots).
// Usage: node scripts/capture_pages.mjs  (frontend dev server + backend must be up)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = path.resolve(__dirname, "..");
const SHOTS = path.join(BASE, "docs", "phase1-screenshots");
const BACKEND = process.env.TRADESENSE_BACKEND_PORT || "8001";
const FRONTEND = process.env.TRADESENSE_FRONTEND_PORT || "5173";
const API = `http://127.0.0.1:${BACKEND}/api`;

const PAGES = [
  ["01-login", "/login", false, "text=登录工作台"],
  ["02-dashboard", "/", true, "text=待处理询盘"],
  ["03-inquiry-detail", null, true, null], // inquiry id filled at runtime
  ["04-products", "/products", true, "text=TS-"],
  ["05-inquiry-list", "/inquiries", true, "table"],
  ["06-connectors", "/connectors", true, null],
  ["07-analytics", "/analytics", true, "text=渠道与响应"],
  ["08-import", "/products/import", true, null],
  ["09-glossary", "/glossary", true, null],
  ["10-followups", "/followups", true, null],
  ["11-knowledge", "/knowledge", true, "text=新建条目"],
  ["13-shipment-detail", "/shipments/1", true, null],
  ["12-settings", "/settings", true, "text=用户管理"],
];

async function token() {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "demo@tradesense-demo.cn", password: "demo1234" }),
  });
  return (await r.json()).access_token;
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  const tk = await token();
  const inq = await fetch(`${API}/inquiries?q=German%20market`, {
    headers: { Authorization: `Bearer ${tk}` },
  }).then((r) => r.json());
  const iid = inq.items?.[0]?.id ?? 1;

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let ok = 0;
  for (const [name, rawPath, withToken, waitFor] of PAGES) {
    const route = rawPath === null ? `/inquiries/${iid}` : rawPath;
    if (withToken) {
      await page.addInitScript((t) => localStorage.setItem("tradesense_token", t), tk);
    }
    await page.goto(`http://127.0.0.1:${FRONTEND}${route}`, { waitUntil: "networkidle" });
    if (waitFor) {
      try {
        await page.waitForSelector(waitFor, { timeout: 15_000 });
      } catch {
        console.log(`FAIL ${name} (wait timeout: ${waitFor})`);
        continue;
      }
    }
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
    console.log(`OK ${name}`);
    ok += 1;
  }
  await browser.close();
  console.log(`${ok}/${PAGES.length} captured`);
  process.exit(ok === PAGES.length ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
