import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Quotes from "../pages/Quotes";
import Connectors from "../pages/Connectors";

const reply = (data: unknown, status = 200) => ({
  ok: status < 400, status, text: async () => JSON.stringify(data),
});

function show(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe("quote and connector workflow regressions", () => {
  it("loads the next quote page and displays the quote currency", async () => {
    const fetch = vi.fn(async (url: string) => {
      const page = url.includes("page=2") ? 2 : 1;
      return reply({ total: 51, items: [{
        id: page, inquiry_id: page, product_id: 1, version: page, status: "draft",
        incoterm: "FOB", currency: page === 1 ? "USD" : "CNY", quantity: 1000,
        unit_cost: 3, unit_price: 4, customer_price: 4.2, total_amount: 4200,
        is_formal: false, valid_until: null, notes: "",
      }] });
    });
    vi.stubGlobal("fetch", fetch);
    show(<Quotes />);
    expect(await screen.findByText("USD 4.20")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText("CNY 4.20")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => url.includes("page=2&page_size=50"))).toBe(true);
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "上一页" }));
    expect(await screen.findByText("USD 4.20")).toBeInTheDocument();
  });

  it("shows connector type load failures without crashing", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes("/types")
      ? reply({ error: { code: "unavailable", message: "渠道类型加载失败" } }, 503)
      : reply({ items: [] })));
    show(<Connectors />);
    expect(await screen.findByText("渠道类型加载失败")).toBeInTheDocument();
  });

  it("distinguishes configured mailboxes from verified connections", async () => {
    let verified = false;
    const account = () => ({ id: 1, connector_type: "email_imap", name: "测试邮箱", mode: "live",
      status: verified ? "connected" : "disconnected", auth_state: verified ? "authorized" : "not_verified",
      last_sync_at: null, last_error: "", label: "邮箱", live_supported: true,
      env_keys: ["IMAP_PASSWORD"], config_nonsecret: {} });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/test")) { verified = true; return reply({ ok: true, authorized: true }); }
      return reply({ items: url.includes("/types") ? [] : [account()] });
    }));
    show(<Connectors />);
    expect(await screen.findByText("待验证")).toBeInTheDocument();
    expect(screen.queryByText("已连接")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(await screen.findByText("已连接")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("待验证")).not.toBeInTheDocument());
  });
});
