import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ShipmentWorkbench from "../pages/ShipmentWorkbench";

const TOKEN = "test-token";
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getToken: () => TOKEN };
});

function shipment(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1, shipment_no: "SH-20260912-0842", order_no: "PO-1", transport_mode: "sea",
    status: "docs_making", port_of_loading: "Ningbo", port_of_discharge: "Hamburg",
    incoterm: "FOB", etd: null, cutoff_at: null, customer_name: "HausKonzept GmbH",
    open_total: 2, high: 1, medium: 1, low: 0, risk: "high", ...overrides,
  };
}

const LIST = { items: [shipment()], total: 1, page: 1, page_size: 50 };

const DETAIL = {
  ...shipment(),
  notes: "", required_docs_json: "[]",
  documents: [
    { id: 10, doc_type: "invoice", version: 1, status: "extracted", original_filename: "inv.pdf", pages: 1, has_text_layer: true, extract_error: "" },
    { id: 11, doc_type: "origin_certificate", version: 1, status: "needs_manual", original_filename: "scan.pdf", pages: 1, has_text_layer: false, extract_error: "未检测到文本层" },
  ],
  issues: [
    {
      id: 100, severity: "high", issue_type: "conflict", rule_code: "amount_vs_lc",
      title: "商业发票金额 USD 48,620.00 与信用证金额 USD 46,820.00 不一致",
      expected_value: "46,820.00", actual_value: "48,620.00",
      evidence: [{ doc_id: 10, doc_type: "invoice", field: "total_amount", page: 1, text: "Total Amount: USD 48,620.00" }],
      status: "open", resolution_note: "",
    },
    {
      id: 101, severity: "high", issue_type: "missing", rule_code: "missing_docs",
      title: "单证缺失：origin_certificate",
      expected_value: "", actual_value: "缺失: origin_certificate",
      evidence: [{ doc_type: "origin_certificate", field: "-", page: null, text: "未上传" }],
      status: "open", resolution_note: "",
    },
  ],
};

function mockFetch(bodyByUrl: (url: string) => unknown) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(bodyByUrl(url))) });
  });
}

function renderWorkbench() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ShipmentWorkbench />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch((url) => {
    if (url.includes("/api/shipments/1")) return DETAIL;
    if (url.includes("/api/shipments")) return LIST;
    return {};
  }));
});

async function openDetail() {
  renderWorkbench();
  await waitFor(() => expect(screen.getByText("SH-20260912-0842")).toBeInTheDocument());
  fireEvent.click(screen.getByText("SH-20260912-0842"));
  await waitFor(() => expect(screen.getByText("单证")).toBeInTheDocument());
}

describe("ShipmentWorkbench", () => {
  it("renders stat band with risk totals once loaded", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("高风险").previousElementSibling).toHaveTextContent("1"));
    expect(screen.getByText("今日待处理").previousElementSibling).toHaveTextContent("2");
  });

  it("lists shipments with ports and issue counts", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("SH-20260912-0842")).toBeInTheDocument());
    expect(screen.getByText("Ningbo → Hamburg")).toBeInTheDocument();
    await waitFor(() => expect(
      screen.getByText((_, el) => el?.textContent === "2 个异常")).toBeInTheDocument());
  });

  it("shows empty state when no shipments", async () => {
    vi.stubGlobal("fetch", mockFetch(() => ({ items: [], total: 0 })));
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("empty")).toBeInTheDocument());
  });

  it("loads detail with issues and evidence on row click", async () => {
    await openDetail();
    await waitFor(() => expect(screen.getAllByText(/与信用证金额/).length).toBeGreaterThan(0));
    expect(screen.getByText(/Total Amount: USD 48,620\.00/)).toBeInTheDocument();
    expect(screen.getByText("单证缺失：origin_certificate")).toBeInTheDocument();
    expect(screen.getAllByText("采纳建议").length).toBe(2);
    // evidence line cites document type + page
    const withEvidence = screen.getAllByText((_, el) =>
      (el?.textContent || "").includes("第1页") && (el?.textContent || "").includes("Total Amount"));
    expect(withEvidence.length).toBeGreaterThan(0);
  });

  it("ignore requires a note before confirming", async () => {
    await openDetail();
    fireEvent.click(screen.getAllByText("忽略并说明")[0]);
    const confirm = screen.getByText("确认忽略").closest("button") as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("忽略理由（必填）"), { target: { value: "客户豁免" } });
    expect((screen.getByText("确认忽略").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });

  it("switches to documents tab with status badges", async () => {
    await openDetail();
    fireEvent.click(screen.getByText("单证"));
    await waitFor(() => expect(screen.getByText("inv.pdf")).toBeInTheDocument());
    expect(screen.getByText("待人工录入")).toBeInTheDocument();
    expect(screen.getAllByText("预览").length).toBe(2);
  });

  it("fields tab shows provenance and manual edit entry", async () => {
    vi.stubGlobal("fetch", mockFetch((url) => {
      if (url.includes("/fields")) {
        return { items: [{ id: 5, doc_type: "invoice", field_name: "total_amount", value: "48,620.00", confidence: 0.9, evidence_page: 1, evidence_text: "Total Amount: USD 48,620.00", source: "extracted" }] };
      }
      if (url.includes("/api/shipments/1")) return DETAIL;
      return LIST;
    }));
    renderWorkbench();
    await waitFor(() => screen.getByText("SH-20260912-0842"));
    fireEvent.click(screen.getByText("SH-20260912-0842"));
    await waitFor(() => expect(screen.getByText("字段对照")).toBeInTheDocument());
    fireEvent.click(screen.getByText("字段对照"));
    await waitFor(() => expect(screen.getByText("48,620.00")).toBeInTheDocument());
    expect(screen.getByText("提取 90%")).toBeInTheDocument();
    expect(screen.getByText("修改")).toBeInTheDocument();
  });

  it("comms tab generates chase email draft", async () => {
    vi.stubGlobal("fetch", mockFetch((url) => {
      if (url.includes("chase-email")) {
        return { id: 9, subject_en: "Urgent: Documents Revision Required",
                 body_en: "Dear partner,\n\n- amount mismatch", body_zh: "催补",
                 needs_confirmation: ["收件人需人工填写"] };
      }
      if (url.includes("/api/shipments/1")) return DETAIL;
      return LIST;
    }));
    renderWorkbench();
    await waitFor(() => screen.getByText("SH-20260912-0842"));
    fireEvent.click(screen.getByText("SH-20260912-0842"));
    await waitFor(() => expect(screen.getByText("沟通记录")).toBeInTheDocument());
    fireEvent.click(screen.getByText("沟通记录"));
    fireEvent.click(screen.getByText(/生成催补\/改单邮件草稿/));
    await waitFor(() => expect(screen.getByText("Urgent: Documents Revision Required")).toBeInTheDocument());
    expect(screen.getByText(/amount mismatch/)).toBeInTheDocument();
  });
});
