import "@testing-library/jest-dom/vitest";

// Recharts ResponsiveContainer 需要 ResizeObserver（jsdom 未内置）
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverStub;
