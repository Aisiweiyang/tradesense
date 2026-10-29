import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getToken: () => "tok" };
});

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input).replace("/api", "");
    for (const key of Object.keys(routes)) {
      if (url.startsWith(key) || url === key) {
        return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(routes[key])) });
      }
    }
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ items: [], total: 0 })) });
  });
}

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

let fetchMock: ReturnType<typeof mockFetch>;

beforeEach(() => {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => (fetchMock as ReturnType<typeof mockFetch>)(input));
});

describe("pages smoke", () => {
  it("Products 列表渲染产品与阶梯价", async () => {
    fetchMock = mockFetch({
      "/products": {
        items: [{
          id: 1, sku: "TS-VB-001", name_en: "Vacuum Bottle", name_zh: "保温杯",
          category: "insulated_bottle", material: "stainless steel", spec: "500ml",
          moq: 500, price_tiers_json: '[{"min_qty":500,"unit_price":3.2}]',
          currency: "USD", lead_time_days: 25, certifications_json: '["FDA","LFGB"]',
          is_active: true, data_source: "seed",
        }],
        total: 1, categories: ["insulated_bottle"],
      },
    });
    const { default: Products } = await import("../pages/Products");
    renderPage(<Products />);
    await waitFor(() => expect(screen.getByText("Vacuum Bottle")).toBeInTheDocument());
    expect(screen.getByText(/500\+:?\$3\.2|500\+:\$3\.2/)).toBeTruthy();
    expect(screen.getByText("TS-VB-001")).toBeInTheDocument();
  });

  it("Inquiries 列表显示完整度与渠道", async () => {
    fetchMock = mockFetch({
      "/inquiries": {
        items: [{
          id: 9, title: "hi", status: "open", language: "en", completeness: 10,
          quality_flag: "low_quality", source_channel: "webform",
          customer_name: "win", country: "", updated_at: "2026-09-13T00:00:00Z",
        }],
        total: 1,
      },
    });
    const { default: Inquiries } = await import("../pages/Inquiries");
    renderPage(<Inquiries />);
    await waitFor(() => expect(screen.getByText("hi")).toBeInTheDocument());
    expect(screen.getByText(/低质量/)).toBeInTheDocument();
    expect(screen.getByText(/网站表单|webform/)).toBeTruthy();
  });

  it("Glossary 渲染术语与免责声明", async () => {
    fetchMock = mockFetch({
      "/glossary": { items: [{ term: "FOB", zh: "离岸价说明", en: "Free On Board" }],
                     disclaimer: "仅供参考" },
    });
    const { default: Glossary } = await import("../pages/Glossary");
    renderPage(<Glossary />);
    await waitFor(() => expect(screen.getByText("FOB")).toBeInTheDocument());
    expect(screen.getByText(/离岸价说明/)).toBeInTheDocument();
    expect(screen.getByText(/仅供参考/)).toBeInTheDocument();
  });

  it("Audit 渲染审计记录", async () => {
    fetchMock = mockFetch({
      "/audit": { items: [{ id: 1, action: "quote.approve", entity_type: "quote",
                            entity_id: "3", detail: {}, user: "张外贸",
                            created_at: "2026-09-13T00:00:00Z" }], total: 1 },
    });
    const { default: Audit } = await import("../pages/Audit");
    renderPage(<Audit />);
    await waitFor(() => expect(screen.getByText("quote.approve")).toBeInTheDocument());
  });

  it("SyncLogs 渲染同步事件与外部消息", async () => {
    fetchMock = mockFetch({
      "/sync-logs": {
        items: [{ id: 1, account: "演示邮箱", level: "error", event: "sync_error",
                  detail: { error: "IMAP 超时" }, created_at: "2026-09-13T00:00:00Z" }],
        recent_messages: [{ id: 5, channel: "email_imap", sender: "a@b.cn",
                            status: "duplicate", inquiry_id: null, received_at: null }],
        total: 1,
      },
    });
    const { default: SyncLogs } = await import("../pages/SyncLogs");
    renderPage(<SyncLogs />);
    await waitFor(() => expect(screen.getByText("sync_error")).toBeInTheDocument());
    expect(screen.getByText("重复")).toBeInTheDocument();
  });

  it("Suppliers 渲染供应商与可靠性", async () => {
    fetchMock = mockFetch({
      "/suppliers": { items: [{ id: 1, name: "永康五金厂", region: "浙江", contact_name: "李经理",
                                email: "", reliability_score: 0.85, notes: "", is_active: true }] },
    });
    const { default: Suppliers } = await import("../pages/Suppliers");
    renderPage(<Suppliers />);
    await waitFor(() => expect(screen.getByText("永康五金厂")).toBeInTheDocument());
    expect(screen.getByText("85")).toBeInTheDocument();
  });

  it("Quotes 渲染报价版本与内部成本", async () => {
    fetchMock = mockFetch({
      "/quotes": { items: [{ id: 3, inquiry_id: 7, product_id: 2, version: 2, status: "approved",
                             incoterm: "FOB", currency: "USD", quantity: 1000, unit_cost: 3.51,
                             unit_price: 4.13, customer_price: 4.2, total_amount: 4200,
                             is_formal: true, valid_until: "2026-10-13T00:00:00Z", notes: "" }],
                   total: 1 },
    });
    const { default: Quotes } = await import("../pages/Quotes");
    renderPage(<Quotes />);
    await waitFor(() => expect(screen.getByText("v2")).toBeInTheDocument());
    expect(screen.getByText("USD 4.20")).toBeInTheDocument();
  });

  it("Today 渲染待办任务分组", async () => {
    fetchMock = mockFetch({
      "/followups/workload": {
        overdue: [{ id: 1, title: "超期任务", task_type: "follow_up", due_at: null,
                    status: "pending", priority: "high", reason_json: "{}", inquiry_id: null }],
        today_due: [],
        quoted_no_reply: [], long_silence: [], high_intent: [], incomplete: [],
      },
    });
    const { default: Today } = await import("../pages/Today");
    renderPage(<Today />);
    await waitFor(() => expect(screen.getByText("超期任务")).toBeInTheDocument());
  });
});
