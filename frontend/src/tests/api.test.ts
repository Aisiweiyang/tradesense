import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, clearToken, getToken, setToken } from "../api/client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

afterEach(() => clearToken());

describe("api client", () => {
  it("attaches bearer token and parses JSON", async () => {
    setToken("tok-123");
    const fetchMock = mockFetch(200, { hello: "world" });
    vi.stubGlobal("fetch", fetchMock);
    const data = await api<{ hello: string }>("/products");
    expect(data.hello).toBe("world");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });

  it("throws ApiError with unified envelope", async () => {
    vi.stubGlobal("fetch", mockFetch(404, { error: { code: "not_found", message: "询盘不存在" } }));
    const err = await api("/inquiries/999").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("not_found");
    expect((err as ApiError).message).toBe("询盘不存在");
  });

  it("serializes JSON bodies with content-type", async () => {
    const fetchMock = mockFetch(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await api("/inquiries", { method: "POST", body: JSON.stringify({ text: "hi" }) });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});
