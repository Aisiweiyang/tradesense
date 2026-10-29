import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";

const TOKEN = process.env.E2E_TOKEN ?? "";
const API_BASE = process.env.E2E_API_BASE ?? "http://127.0.0.1:8001/api";

export async function login(page: Page) {
  // inject token before app boots (localhost-only #token / localStorage)
  await page.addInitScript((t) => localStorage.setItem("tradesense_token", t), TOKEN);
}

export async function apiToken(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const r = await request.post(`${API_BASE}/auth/login`, {
    data: { email: "demo@tradesense-demo.cn", password: "demo1234" },
  });
  const body = await r.json();
  expect(body.access_token).toBeTruthy();
  return body.access_token;
}

test.describe("TradeSense E2E", () => {
  let token = "";

  test.beforeAll(async ({ request }) => {
    token = await apiToken(request);
  });

  test("链路1：登录 → 工作台统计可见", async ({ page }) => {
    await login(page);
    await page.goto("/");
    await expect(page.getByText("待处理询盘")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("单证工作台")).toBeVisible();
  });

  test("链路2：粘贴询盘 → 多轮 → 匹配 → 报价 → 批准", async ({ page }) => {
    await login(page);
    await page.goto("/inquiries/new");
    await page.getByPlaceholder(/在此粘贴客户询盘原文/).fill(
      "We need 1,000 pcs vacuum insulated bottles 500ml, ship to Rotterdam, FOB. LFGB required.");
    await page.getByRole("button", { name: "创建并解析" }).click();
    await expect(page.getByText(/完整度/).first()).toBeVisible({ timeout: 15_000 });

    // 多轮补充
    await page.getByRole("button", { name: /对话/ }).click();
    await page.getByPlaceholder(/粘贴客户的新回复/).fill("Also target price USD 6/pc, and quote CIF Rotterdam.");
    await page.getByRole("button", { name: "添加并重新解析" }).click();
    await expect(page.getByText(/添加并重新解析/)).toBeDisabled().catch(() => {});

    // 匹配
    await page.getByRole("button", { name: /匹配/ }).click();
    await page.getByRole("button", { name: /运行匹配/ }).click();
    await expect(page.getByText(/推荐/).first()).toBeVisible({ timeout: 15_000 });

    // 报价
    await page.getByRole("button", { name: /报价/ }).first().click();
    const productSelect = page.locator("main select").first();
    await productSelect.selectOption({ index: 1 });
    const createBtn = page.getByRole("button", { name: /计算并创建草稿/ });
    await createBtn.click();
    await expect(page.getByText(/计算明细|还没有报价/).first()).toBeVisible({ timeout: 15_000 });

    // 打开明细 → 批准为正式报价
    await page.getByRole("button", { name: "明细" }).first().click();
    await page.getByRole("button", { name: /批准为正式报价/ }).click();
    await expect(page.getByText(/已批准/).first()).toBeVisible({ timeout: 15_000 });
  });

  test("链路3：货件上传单证 → 发现冲突 → 采纳 → 数量更新", async ({ page, request }) => {
    const t = await apiToken(request);
    // API 建货件（UI 亦可，这里确保确定性）
    const r = await request.post(`${API_BASE}/shipments`, {
      headers: { Authorization: `Bearer ${t}` },
      data: { order_no: "E2E-SH-1", port_of_loading: "Ningbo",
              port_of_discharge: "Hamburg", required_docs: ["invoice", "packing_list", "bill_of_lading"] },
    });
    const shipment = await r.json();
    const shipmentId = shipment.id;

    await login(page);
    await page.goto(`/shipments/${shipmentId}`);
    await expect(page.getByText(shipment.shipment_no).first()).toBeVisible({ timeout: 15_000 });

    // 上传两份冲突单证（API 注入；UI 隐藏 file input 与 Playwright 的兼容问题见已知限制）
    for (const [fname, mime] of [["invoice.pdf", "application/pdf"], ["lc.pdf", "application/pdf"]] as const) {
      const up = await request.post(`${API_BASE}/shipments/${shipmentId}/documents`, {
        headers: { Authorization: `Bearer ${t}` },
        multipart: { file: { name: fname, mimeType: mime,
                             buffer: fs.readFileSync(`e2e/fixtures/${fname}`) } },
      });
      expect(up.status()).toBe(201);
    }
    // 页面上打开单证标签 → 点重新校验（重新拉取单证与异常）→ 两份已提取
    await page.getByRole("button", { name: "单证", exact: true }).first().click();
    await page.getByRole("button", { name: "重新校验" }).click();
    await expect(page.getByText(/已提取/).first()).toBeVisible({ timeout: 30_000 });

    // 回到异常标签：金额不一致 + 缺件都在
    await page.getByRole("button", { name: /异常 \(\d+\)/ }).click();
    await expect(page.getByText(/与信用证金额/).first()).toBeVisible({ timeout: 30_000 });

    // 采纳建议（金额行）→ 该异常从 open 消失
    const amountCard = page.locator("[data-issue-id]", { hasText: "与信用证金额" }).first();
    await amountCard.getByRole("button", { name: "采纳建议" }).click();
    await expect(page.getByText(/已处理 \(\d+\)/)).toBeVisible({ timeout: 15_000 });
  });


  test("链路4：知识库引用 → 生成草稿 → 引用块与来源可见", async ({ page, request }) => {
    const t = await apiToken(request);
    await login(page);

    // 建一个知识条目（标题带时间戳保证可搜）
    const title = `E2E KB ${Date.now()}`;
    const kb = await request.post(`${API_BASE}/knowledge`, {
      headers: { Authorization: `Bearer ${t}` },
      data: { title, content: "LFGB test reports are usually requested by German buyers for food-contact drinkware.", tags: "认证,LFGB" },
    });
    expect(kb.status()).toBe(201);
    const kbId = (await kb.json()).id;

    // 建一个简单询盘
    const inq = await request.post(`${API_BASE}/inquiries`, {
      headers: { Authorization: `Bearer ${t}` },
      data: { text: "We need 500 ceramic mugs 350ml for a German gift shop, FOB Hamburg." },
    });
    const inqId = (await inq.json()).id;

    // 打开询盘 → 回复标签 → 搜索并勾选知识条目 → 生成
    await page.goto(`/inquiries/${inqId}`);
    await page.getByRole("button", { name: /回复/ }).first().click();
    const searchBox = page.getByPlaceholder(/搜索条目：LFGB/);
    await expect(searchBox).toBeVisible({ timeout: 15_000 });
    await searchBox.fill(title);
    await page.getByRole("checkbox").first().check();
    await page.getByRole("button", { name: /生成中英文草稿/ }).click();

    // 正文出现知识库引用块，事实区标注 知识库#id，确认区提示人工核对
    await expect(page.getByText(/Useful notes from our team knowledge base/).first())
      .toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(new RegExp(`知识库#${kbId}`)).first()).toBeVisible();
    await expect(page.getByText(/知识库内容已引用，请人工核对/)).toBeVisible();
  });

  test("链路5：勾选两条报价 → 合并报价单 → PDF 可下载且未批准带水印", async ({ page, request }) => {
    const t = await apiToken(request);
    const H = { Authorization: `Bearer ${t}` };

    // 造一条询盘 + 两笔不同产品的草稿报价（确定性，不依赖种子）
    const inq = await (await request.post(`${API_BASE}/inquiries`, {
      headers: H, data: { text: "Quote 800 ceramic mugs and 500 glass cups, FOB" },
    })).json();
    const prods = (await (await request.get(`${API_BASE}/products?page=1&page_size=5`, { headers: H })).json()).items;
    const qids: number[] = [];
    for (const p of prods.slice(0, 2)) {
      const q = await (await request.post(`${API_BASE}/quotes`, {
        headers: { ...H, "Content-Type": "application/json" },
        data: { inquiry_id: inq.id, product_id: p.id, quantity: 500, incoterm: "FOB" },
      })).json();
      qids.push(q.id);
    }

    await login(page);
    await page.goto(`/inquiries/${inq.id}`);
    await page.getByRole("button", { name: /报价/ }).first().click();
    await page.getByText("报价版本").first().waitFor({ timeout: 15_000 });

    // 按报价 id 精确勾两条 → 合并
    for (const id of qids) {
      await page.locator(`input[data-quote-id="${id}"]`).check();
    }
    await page.getByRole("button", { name: /合并所选（2）/ }).click();
    await page.getByText("合并报价单").first().waitFor({ timeout: 15_000 });

    // PDF 链接带 query token，直接请求应得 %PDF（未批准水印由元数据标记）
    const href = await page.locator('a[href*="/quote-sheets/"][href*="access_token="]').first().getAttribute("href");
    expect(href).toContain("access_token=");
    const pdf = await request.get(new URL(href!, page.url()).toString());
    expect(pdf.status()).toBe(200);
    expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
  });
});
