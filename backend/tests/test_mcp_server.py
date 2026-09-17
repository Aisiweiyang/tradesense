"""MCP server: protocol behaviors, tool mapping over mocked REST, stdio round-trip."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "mcp"))

import tradesense_mcp as m  # noqa: E402


def _handler():
    return m.MCPHandler(token="test-token")


class _FakeAPI:
    """Stub for MCPHandler._api keyed by (method, path)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, path, payload=None, params=None):
        self.calls.append((method, path, payload, params))
        if path not in self.routes:
            raise RuntimeError(f"HTTP 404: no route for {method} {path}")
        return self.routes[path]


def test_protocol_basics():
    h = _handler()
    init = h.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["protocolVersion"] == m.PROTOCOL_VERSION
    assert init["result"]["serverInfo"]["name"] == "tradesense"
    # notification: no id → no response
    assert h.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = h.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"ts_create_inquiry", "ts_run_match", "ts_create_quote",
            "ts_generate_reply"} <= names
    assert h.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601


def test_tool_error_bubbles_as_isError(monkeypatch):
    h = _handler()

    def boom(method, path, payload=None, params=None):
        raise RuntimeError("HTTP 404: 询盘不存在")
    monkeypatch.setattr(h, "_api", boom)
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "ts_get_inquiry", "arguments": {"inquiry_id": 999}}})
    assert out["result"]["isError"] is True
    assert "HTTP 404" in out["result"]["content"][0]["text"]


def test_unknown_tool_is_error_not_crash():
    h = _handler()
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "nope", "arguments": {}}})
    assert out["result"]["isError"] is True


def test_get_inquiry_surfaces_cannot_quote_reasons(monkeypatch):
    """把"为什么还不能报价"直接交给助手，便于向用户解释阻塞。"""
    h = m.MCPHandler(token="t")
    fake = _FakeAPI({"/inquiries/9": {
        "id": 9, "title": "t", "status": "clarifying", "stage": "clarifying",
        "completeness": 60,
        "requirement": {"fields": {"quantity": {"normalized": "500"}},
                        "cannot_quote_reasons": ["缺少认证要求"]}}})
    monkeypatch.setattr(h, "_api", fake)
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "ts_get_inquiry", "arguments": {"inquiry_id": 9}}})
    body = json.loads(out["result"]["content"][-1]["text"])
    assert body["cannot_quote_reasons"] == ["缺少认证要求"]


def test_create_quote_maps_fields_and_notes_gate(monkeypatch):
    h = _handler()
    fake = _FakeAPI({"/quotes": {"id": 7, "version": 2, "unit_price": 3.2,
                                 "currency": "USD", "total_amount": 3200.0,
                                 "status": "draft"}})
    monkeypatch.setattr(h, "_api", fake)
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "ts_create_quote",
        "arguments": {"inquiry_id": 1, "product_id": 2, "quantity": 1000,
                      "incoterm": "FOB"}}})
    blocks = out["result"]["content"]
    assert "人工" in blocks[0]["text"]  # 说明块在前
    body = json.loads(blocks[-1]["text"])  # 最后一块是 JSON
    assert body["quote_id"] == 7 and body["unit_price"] == 3.2
    method, path, payload, _ = fake.calls[-1]
    assert method == "POST" and path == "/quotes"
    assert payload["quantity"] == 1000


def test_generate_reply_rejects_bad_kind():
    h = _handler()
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "ts_generate_reply",
                               "arguments": {"inquiry_id": 1, "kind": "hack"}}})
    assert out["result"]["isError"] is True


def test_list_inquiries_passes_filters(monkeypatch):
    h = _handler()
    fake = _FakeAPI({"/inquiries": {"total": 1, "items": [
        {"id": 5, "title": "t", "status": "quoted", "stage": "quoted",
         "completeness": 80}]}})
    monkeypatch.setattr(h, "_api", fake)
    out = h.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "ts_list_inquiries", "arguments": {"q": "mug", "stage": "quoted"}}})
    assert json.loads(out["result"]["content"][-1]["text"])["total"] == 1
    _, _, _, params = fake.calls[-1]
    assert params["q"] == "mug" and params["stage"] == "quoted" and params["page"] == 1


def test_stdio_round_trip():
    """真实子进程：initialize → tools/list 逐行 JSON-RPC 往返。"""
    server = Path(__file__).resolve().parent.parent.parent / "mcp" / "tradesense_mcp.py"
    env = {**dict(__import__("os").environ), "TRADESENSE_MCP_TOKEN": "dummy"}
    p = subprocess.Popen([sys.executable, str(server)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, text=True, encoding="utf-8")
    try:
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {}}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        p.stdin.close()
        lines = [json.loads(l) for l in p.stdout.read().splitlines() if l.strip()]
        assert lines[0]["result"]["serverInfo"]["name"] == "tradesense"
        assert len(lines[1]["result"]["tools"]) == 9
    finally:
        p.terminate()
