import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Knowledge from "../pages/Knowledge";
import Settings from "../pages/Settings";
import Analytics from "../pages/Analytics";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getToken: () => "tok" };
});

let fetchMock: ReturnType<typeof mockFetch>;
let log: { m: string; body?: unknown }[];

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    const url = String(input).replace("/api", "").replace(/\/$/, "");
    log.push({ m: `${method} ${url}`, body: init?.body ? JSON.parse(init.body as string) : undefined });
    for (const key of Object.keys(routes)) {
      if (url === key || url.startsWith(key)) {
        return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(routes[key])) });
      }
    }
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ items: [] })) });
  });
}

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      {ui}
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  log = [];
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => (fetchMock)(input, init));
});

const KB_ITEMS = {
  items: [
    { id: 1, title: "欧盟食品接触：LFGB 与 EC 1935/2004", content: "German buyers usually ask for LFGB test reports.", tags: "欧盟,认证,LFGB" },
    { id: 2, title: "木包装出口需 IPPC 熏蒸标识", content: "Solid wood packaging must carry the IPPC mark.", tags: "包装,IPPC" },
  ],
};

describe("知识库页面", () => {
  it("渲染条目、标签并支持搜索", async () => {
    fetchMock = mockFetch({ "/knowledge": KB_ITEMS });
    renderPage(<Knowledge />);
    expect(await screen.findByText("欧盟食品接触：LFGB 与 EC 1935/2004")).toBeInTheDocument();
    expect(screen.getByText("木包装出口需 IPPC 熏蒸标识")).toBeInTheDocument();
    const tag = screen.getByTitle("搜索标签「LFGB」");
    fireEvent.click(tag);
    await waitFor(() => {
      const called = fetchMock.mock.calls.some(([input]) => String(input).includes("q=LFGB"));
      expect(called).toBe(true);
    });
  });

  it("新建条目走弹窗并发 POST", async () => {
    fetchMock = mockFetch({ "/knowledge": KB_ITEMS });
    renderPage(<Knowledge />);
    fireEvent.click(await screen.findByText("新建条目"));
    expect(screen.getByTestId("knowledge-editor")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("标题 *"), { target: { value: "样品政策" } });
    fireEvent.change(screen.getByPlaceholderText(/正文：写清楚适用场景/), { target: { value: "1-2 pcs free" } });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      const post = log.find((x) => x.m === "POST /knowledge");
      expect(post?.body).toMatchObject({ title: "样品政策", content: "1-2 pcs free" });
    });
  });

  it("删除需二次确认", async () => {
    fetchMock = mockFetch({ "/knowledge": KB_ITEMS });
    renderPage(<Knowledge />);
    const delButtons = await screen.findAllByText("删除");
    fireEvent.click(delButtons[0]);
    expect(screen.getByText("确认删除")).toBeInTheDocument();
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(log.some((x) => x.m === "DELETE /knowledge/1")).toBe(true));
  });
});

describe("设置页汇率卡片", () => {
  it("渲染汇率表与更新人", async () => {
    fetchMock = mockFetch({
      "/fx": { items: [{ id: 1, pair: "CNY/USD", base_currency: "CNY", quote_currency: "USD",
                         rate: 0.13888889, updated_by_name: "张外贸", updated_at: "2026-09-15T10:00:00Z" }] },
    });
    renderPage(<Settings />);
    expect(await screen.findByText("CNY/USD")).toBeInTheDocument();
    expect(screen.getByText(/张外贸/)).toBeInTheDocument();
  });

  it("保存汇率发 PUT 并做大小写归一", async () => {
    fetchMock = mockFetch({ "/fx": { items: [] } });
    renderPage(<Settings />);
    fireEvent.change(await screen.findByPlaceholderText("基准币种"), { target: { value: "usd" } });
    fireEvent.change(screen.getByPlaceholderText("目标币种"), { target: { value: "cny" } });
    fireEvent.change(screen.getByPlaceholderText("汇率，如 7.2"), { target: { value: "7.2" } });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      const put = log.find((x) => x.m === "PUT /fx");
      expect(put?.body).toMatchObject({ base_currency: "USD", quote_currency: "CNY", rate: 7.2 });
    });
  });

  it("无权限时显示提示而不是报错", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve({
      ok: false, status: 403,
      text: () => Promise.resolve(JSON.stringify({ error: { code: "forbidden", message: "需要 manager 及以上角色" } })),
    })));
    renderPage(<Settings />);
    expect(await screen.findByText(/汇率配置仅管理员/)).toBeInTheDocument();
  });
});

describe("数据看板销售漏斗", () => {
  it("渲染漏斗各阶段、转化率与停留时长", async () => {
    fetchMock = mockFetch({
      "/analytics/insights": {
        channels: [],
        first_response: { median_hours: null, responded: 0, waiting: 0, longest_waiting_hours: null },
        target_hit: { hit: 0, total: 0, rate: null },
      },
      "/dashboard/analytics": {
        inquiry_total: 5, stage_counts: {}, channel_counts: {},
        completeness_buckets: {}, quote_total: 2, approved_quote_amount: 100,
      },
      "/analytics/funnel": {
        stages: [
          { stage: "new", label: "新询盘", count: 3, reached: 5, conversion_to_next: 0.4, next_stage: "qualified", median_dwell_hours: 91.5 },
          { stage: "qualified", label: "有效线索", count: 1, reached: 2, conversion_to_next: 0.5, next_stage: "clarifying", median_dwell_hours: 20 },
          { stage: "clarifying", label: "澄清中", count: 1, reached: 1, conversion_to_next: 1.0, next_stage: "quoted", median_dwell_hours: 30 },
          { stage: "quoted", label: "已报价", count: 1, reached: 1, conversion_to_next: 1.0, next_stage: "sample", median_dwell_hours: 40 },
          { stage: "sample", label: "寄样中", count: 0, reached: 0, conversion_to_next: null, next_stage: "negotiating", median_dwell_hours: null },
          { stage: "negotiating", label: "谈判中", count: 0, reached: 0, conversion_to_next: null, next_stage: "won", median_dwell_hours: null },
          { stage: "won", label: "已成交", count: 0, reached: 0, conversion_to_next: null, next_stage: null, median_dwell_hours: null },
          { stage: "lost", label: "已失败", count: 1, reached: 0, conversion_to_next: null, next_stage: null, median_dwell_hours: null },
          { stage: "dormant", label: "休眠", count: 0, reached: 0, conversion_to_next: null, next_stage: null, median_dwell_hours: null },
        ],
      },
    });
    renderPage(<Analytics />);
    expect(await screen.findByText("有效线索")).toBeInTheDocument();
    expect(screen.getByText("销售漏斗")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("3.8 天")).toBeInTheDocument();
    expect(screen.getByText("20 小时")).toBeInTheDocument();
    // 点击阶段行显示口径说明
    fireEvent.click(screen.getByText("有效线索"));
    expect(await screen.findByText(/历史上有 2 个询盘进入过该阶段/)).toBeInTheDocument();
  });
});
