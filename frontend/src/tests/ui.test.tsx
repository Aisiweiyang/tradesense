import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CompletenessRing, Badge, EmptyState, ErrorState, Pagination } from "../components/ui";
import { I18nProvider, useI18n } from "../i18n";

describe("CompletenessRing", () => {
  it("renders score and uses color tiers", () => {
    const { container, rerender } = render(<CompletenessRing score={85} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "85");
    expect(container.textContent).toContain("85%");
    expect(container.innerHTML).toContain("#10b981"); // high → green
    rerender(<CompletenessRing score={30} />);
    expect(container.innerHTML).toContain("#ef4444"); // low → red
  });
});

describe("Badge", () => {
  it("maps known statuses to semantic colors and custom text", () => {
    render(<Badge value="conflicting" text="矛盾" />);
    const el = screen.getByText("矛盾");
    expect(el.className).toContain("bg-red-50");
    expect(el.className).toContain("text-red-600");
  });
  it("falls back to a neutral color for unknown values", () => {
    render(<Badge value="whatever_xyz" />);
    expect(screen.getByText("whatever_xyz").className).toContain("bg-slate-100");
  });
});

describe("EmptyState / ErrorState", () => {
  it("shows empty hint", () => {
    render(<EmptyState text="还没有询盘" />);
    expect(screen.getByTestId("empty")).toHaveTextContent("还没有询盘");
  });
  it("shows error and retry", () => {
    render(<ErrorState message="服务器错误" onRetry={() => {}} />);
    expect(screen.getByTestId("error-state")).toHaveTextContent("服务器错误");
    expect(screen.getByText("重试")).toBeInTheDocument();
  });
});

describe("Pagination", () => {
  it("hides when empty and disables prev on first page", () => {
    const { container: empty } = render(<Pagination page={1} pageSize={20} total={0} onPage={() => {}} />);
    expect(empty.textContent).toBe("");
    render(<Pagination page={1} pageSize={20} total={45} onPage={() => {}} />);
    expect(screen.getByText(/共 45 条/)).toBeInTheDocument();
    expect((screen.getByText("上一页") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("下一页") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("i18n", () => {
  function Probe() {
    const { t, locale, setLocale } = useI18n();
    return (
      <div>
        <span data-testid="nav">{t("nav_dashboard")}</span>
        <span data-testid="locale">{locale}</span>
        <button onClick={() => setLocale("en-US")}>switch</button>
      </div>
    );
  }
  it("defaults to zh-CN and falls back for missing keys", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByTestId("nav").textContent).toBe("工作台");
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
  });
  it("switches locale to en-US", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    fireEvent.click(screen.getByText("switch"));
    expect(screen.getByTestId("nav").textContent).toBe("Workbench");
  });
});
