# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> TradeSense E2E >> 链路3：货件上传单证 → 发现冲突 → 采纳 → 数量更新
- Location: e2e\e2e.spec.ts:67:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('SH-20260913-0007').first()
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByText('SH-20260913-0007').first() with timeout 15000ms
  - waiting for getByText('SH-20260913-0007').first()

```

```yaml
- text: 🌊
- heading "TradeSense" [level=1]
- paragraph: 外贸询盘 · 客户跟进 · 产品匹配 · 报价辅助
- text: 邮箱
- textbox "邮箱":
  - /placeholder: you@company.cn
  - text: demo@tradesense-demo.cn
- text: 密码
- textbox "密码":
  - /placeholder: ••••••••
- button "登录"
- text: 演示账号：demo@tradesense-demo.cn / demo1234
```

# Test source

```ts
  1   | import fs from "node:fs";
  2   | import { expect, test, type Page } from "@playwright/test";
  3   | 
  4   | const TOKEN = process.env.E2E_TOKEN ?? "";
  5   | 
  6   | export async function login(page: Page) {
  7   |   // inject token before app boots (localhost-only #token / localStorage)
  8   |   await page.addInitScript((t) => localStorage.setItem("tradesense_token", t), TOKEN);
  9   | }
  10  | 
  11  | export async function apiToken(request: import("@playwright/test").APIRequestContext): Promise<string> {
  12  |   const r = await request.post("http://127.0.0.1:8000/api/auth/login", {
  13  |     data: { email: "demo@tradesense-demo.cn", password: "demo1234" },
  14  |   });
  15  |   const body = await r.json();
  16  |   expect(body.access_token).toBeTruthy();
  17  |   return body.access_token;
  18  | }
  19  | 
  20  | test.describe("TradeSense E2E", () => {
  21  |   let token = "";
  22  | 
  23  |   test.beforeAll(async ({ request }) => {
  24  |     token = await apiToken(request);
  25  |   });
  26  | 
  27  |   test("链路1：登录 → 工作台统计可见", async ({ page }) => {
  28  |     await login(page);
  29  |     await page.goto("/");
  30  |     await expect(page.getByText("待处理询盘")).toBeVisible({ timeout: 15_000 });
  31  |     await expect(page.getByText("单证工作台")).toBeVisible();
  32  |   });
  33  | 
  34  |   test("链路2：粘贴询盘 → 多轮 → 匹配 → 报价 → 批准", async ({ page }) => {
  35  |     await login(page);
  36  |     await page.goto("/inquiries/new");
  37  |     await page.getByPlaceholder(/在此粘贴客户询盘原文/).fill(
  38  |       "We need 1,000 pcs vacuum insulated bottles 500ml, ship to Rotterdam, FOB. LFGB required.");
  39  |     await page.getByRole("button", { name: "创建并解析" }).click();
  40  |     await expect(page.getByText(/完整度/).first()).toBeVisible({ timeout: 15_000 });
  41  | 
  42  |     // 多轮补充
  43  |     await page.getByRole("button", { name: /对话/ }).click();
  44  |     await page.getByPlaceholder(/粘贴客户的新回复/).fill("Also target price USD 6/pc, and quote CIF Rotterdam.");
  45  |     await page.getByRole("button", { name: "添加并重新解析" }).click();
  46  |     await expect(page.getByText(/添加并重新解析/)).toBeDisabled().catch(() => {});
  47  | 
  48  |     // 匹配
  49  |     await page.getByRole("button", { name: /匹配/ }).click();
  50  |     await page.getByRole("button", { name: /运行匹配/ }).click();
  51  |     await expect(page.getByText(/推荐/).first()).toBeVisible({ timeout: 15_000 });
  52  | 
  53  |     // 报价
  54  |     await page.getByRole("button", { name: /报价/ }).first().click();
  55  |     const productSelect = page.locator("main select").first();
  56  |     await productSelect.selectOption({ index: 1 });
  57  |     const createBtn = page.getByRole("button", { name: /计算并创建草稿/ });
  58  |     await createBtn.click();
  59  |     await expect(page.getByText(/计算明细|还没有报价/).first()).toBeVisible({ timeout: 15_000 });
  60  | 
  61  |     // 打开明细 → 批准为正式报价
  62  |     await page.getByRole("button", { name: "明细" }).first().click();
  63  |     await page.getByRole("button", { name: /批准为正式报价/ }).click();
  64  |     await expect(page.getByText(/已批准/).first()).toBeVisible({ timeout: 15_000 });
  65  |   });
  66  | 
  67  |   test("链路3：货件上传单证 → 发现冲突 → 采纳 → 数量更新", async ({ page, request }) => {
  68  |     const t = await apiToken(request);
  69  |     // API 建货件（UI 亦可，这里确保确定性）
  70  |     const r = await request.post("http://127.0.0.1:8000/api/shipments", {
  71  |       headers: { Authorization: `Bearer ${t}` },
  72  |       data: { order_no: "E2E-SH-1", port_of_loading: "Ningbo",
  73  |               port_of_discharge: "Hamburg", required_docs: ["invoice", "packing_list", "bill_of_lading"] },
  74  |     });
  75  |     const shipment = await r.json();
  76  |     const shipmentId = shipment.id;
  77  | 
  78  |     await login(page);
  79  |     await page.goto(`/shipments/${shipmentId}`);
> 80  |     await expect(page.getByText(shipment.shipment_no).first()).toBeVisible({ timeout: 15_000 });
      |                                                                ^ Error: expect(locator).toBeVisible() failed
  81  | 
  82  |     // 上传两份冲突单证（API 注入；UI 隐藏 file input 与 Playwright 的兼容问题见已知限制）
  83  |     for (const [fname, mime] of [["invoice.pdf", "application/pdf"], ["lc.pdf", "application/pdf"]] as const) {
  84  |       const up = await request.post(`http://127.0.0.1:8000/api/shipments/${shipmentId}/documents`, {
  85  |         headers: { Authorization: `Bearer ${t}` },
  86  |         multipart: { file: { name: fname, mimeType: mime,
  87  |                              buffer: fs.readFileSync(`e2e/fixtures/${fname}`) } },
  88  |       });
  89  |       expect(up.status()).toBe(201);
  90  |     }
  91  |     // 页面上打开单证标签 → 点重新校验（重新拉取单证与异常）→ 两份已提取
  92  |     await page.getByRole("button", { name: "单证", exact: true }).first().click();
  93  |     await page.getByRole("button", { name: "重新校验" }).click();
  94  |     await expect(page.getByText(/已提取/).first()).toBeVisible({ timeout: 30_000 });
  95  | 
  96  |     // 回到异常标签：金额不一致 + 缺件都在
  97  |     await page.getByRole("button", { name: /异常 \(\d+\)/ }).click();
  98  |     await expect(page.getByText(/与信用证金额/).first()).toBeVisible({ timeout: 30_000 });
  99  | 
  100 |     // 采纳建议（金额行）→ 该异常从 open 消失
  101 |     const amountCard = page.locator("[data-issue-id]", { hasText: "与信用证金额" }).first();
  102 |     await amountCard.getByRole("button", { name: "采纳建议" }).click();
  103 |     await expect(page.getByText(/已处理 \(\d+\)/)).toBeVisible({ timeout: 15_000 });
  104 |   });
  105 | });
  106 | 
```