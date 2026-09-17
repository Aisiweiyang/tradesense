"""TradeSense MCP server — exposes the deterministic core as MCP tools.

Any MCP-capable AI assistant (Claude, ChatGPT desktop, IDE agents) can
operate TradeSense: create inquiries, run matching, draft deterministic
quotes, generate reply drafts, read funnel/insights. The assistant is just
another client: every call goes through the REST API with a personal access
token, so RBAC, org isolation, audit logs and the never-auto-send rule all
still apply.

Run (backend must be up):
    TRADESENSE_MCP_TOKEN=<jwt> python mcp/tradesense_mcp.py

Protocol: MCP 2024-11-05 over stdio (one JSON-RPC message per line).
Zero dependencies beyond httpx (already a backend requirement).
"""
from __future__ import annotations

import json
import os
import sys

import httpx

API_BASE = os.environ.get("TRADESENSE_MCP_API", "http://127.0.0.1:8001/api")
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "tradesense", "version": "1.0.0"}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


def _s(**props) -> dict:
    return {name: {"type": typ} for name, typ in props.items()}


TOOLS = [
    {"name": "ts_create_inquiry",
     "description": "Create a TradeSense inquiry from raw customer text (parses requirements). "
                    "Returns inquiry id, completeness and AI intake summary.",
     "inputSchema": _schema(_s(text="string", source_channel="string"), ["text"])},
    {"name": "ts_get_inquiry",
     "description": "Fetch one inquiry: status, stage, completeness, confirmed/missing requirement fields.",
     "inputSchema": _schema(_s(inquiry_id="integer"), ["inquiry_id"])},
    {"name": "ts_list_inquiries",
     "description": "Search inquiries by free text and optional status/stage filter.",
     "inputSchema": _schema(_s(q="string", status="string", stage="string"))},
    {"name": "ts_run_match",
     "description": "Run deterministic product matching for an inquiry. Returns ranked candidates "
                    "with met/unmet conditions and rejection reasons.",
     "inputSchema": _schema(_s(inquiry_id="integer"), ["inquiry_id"])},
    {"name": "ts_create_quote",
     "description": "Create a deterministic quote draft (price computed by program, never AI). "
                    "Becomes formal only after human approval inside TradeSense.",
     "inputSchema": _schema(_s(inquiry_id="integer", product_id="integer", quantity="integer",
                               incoterm="string", margin_rate="number"),
                            ["inquiry_id", "product_id", "quantity"])},
    {"name": "ts_funnel",
     "description": "Nine-stage sales funnel: reached, step conversion, median stage dwell.",
     "inputSchema": _schema({})},
    {"name": "ts_insights",
     "description": "Channel conversion, first-response median, target-price hit rate.",
     "inputSchema": _schema({})},
    {"name": "ts_today",
     "description": "Today's follow-up workload: due tasks, quoted-no-reply, long silence, expired quotes.",
     "inputSchema": _schema({})},
    {"name": "ts_generate_reply",
     "description": "Generate a reply draft (10 kinds x 3 tones, EN body with ZH parallel). "
                    "Drafts are never sent automatically; a human approves then sends manually.",
     "inputSchema": _schema(_s(inquiry_id="integer", kind="string", tone="string"),
                            ["inquiry_id", "kind"])},
]

KINDS = ("first_reply,ask_missing_info,product_recommend,sample,quote_send,"
         "quote_follow_up,delay_notice,alternative_offer,polite_rejection,reactivation")


def _text(result, note: str = "") -> dict:
    body = json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result
    blocks = ([{"type": "text", "text": note}] if note else [])
    blocks.append({"type": "text", "text": body})
    return {"content": blocks}


class MCPHandler:
    """Protocol handling separated from I/O so tests can drive it directly."""

    def __init__(self, api_base: str = API_BASE, token: str = ""):
        self.api_base = api_base.rstrip("/")
        self.token = token

    def _api(self, method: str, path: str, payload: dict | None = None,
             params: dict | None = None) -> dict:
        r = httpx.request(method, f"{self.api_base}{path}",
                          headers={"Authorization": f"Bearer {self.token}"},
                          json=payload, params=params, timeout=30)
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", {}).get("message", r.text[:200])
            except Exception:  # noqa: BLE001
                detail = r.text[:200]
            raise RuntimeError(f"HTTP {r.status_code}: {detail}")
        return r.json()

    # ------------------------------------------------------------ tool impls
    def _tool_call(self, name: str, args: dict) -> dict:
        if name == "ts_create_inquiry":
            out = self._api("POST", "/inquiries",
                            {"text": args["text"],
                             "source_channel": args.get("source_channel", "manual")})
            return _text({"inquiry_id": out["id"], "status": out["status"],
                          "stage": out["stage"], "completeness": out.get("completeness"),
                          "ai_intake": out.get("ai_intake")},
                         note="询盘已创建；字段建议需人工确认。")
        if name == "ts_get_inquiry":
            d = self._api("GET", f"/inquiries/{args['inquiry_id']}")
            req = d.get("requirement") or {}
            return _text({"id": d["id"], "title": d["title"], "status": d["status"],
                          "stage": d["stage"], "completeness": d.get("completeness"),
                          "requirement": req.get("fields", req)})
        if name == "ts_list_inquiries":
            params = {k: v for k, v in args.items() if v}
            params.setdefault("page", 1)
            params.setdefault("page_size", 10)
            out = self._api("GET", "/inquiries", params=params)
            return _text({"total": out["total"],
                          "items": [{"id": i["id"], "title": i["title"], "status": i["status"],
                                     "stage": i["stage"], "completeness": i["completeness"]}
                                    for i in out["items"]]})
        if name == "ts_run_match":
            out = self._api("POST", f"/inquiries/{args['inquiry_id']}/match")
            return _text(out, note="匹配为确定性重排序，硬条件淘汰带原因。")
        if name == "ts_create_quote":
            payload = {"inquiry_id": args["inquiry_id"], "product_id": args["product_id"],
                       "quantity": args["quantity"]}
            if args.get("incoterm"):
                payload["incoterm"] = args["incoterm"]
            if args.get("margin_rate") is not None:
                payload["margin_rate"] = args["margin_rate"]
            out = self._api("POST", "/quotes", payload)
            return _text({"quote_id": out["id"], "version": out["version"],
                          "unit_price": out["unit_price"], "currency": out["currency"],
                          "total": out["total_amount"], "status": out["status"]},
                         note="草稿报价，程序计算；正式报价需人工在 TradeSense 中批准。")
        if name == "ts_funnel":
            return _text(self._api("GET", "/analytics/funnel"))
        if name == "ts_insights":
            return _text(self._api("GET", "/analytics/insights"))
        if name == "ts_today":
            return _text(self._api("GET", "/followups/workload"))
        if name == "ts_generate_reply":
            kind = args["kind"]
            if kind not in KINDS.split(","):
                return {"content": [{"type": "text", "text": f"kind 必须是：{KINDS}"}],
                        "isError": True}
            out = self._api("POST", "/replies/generate",
                            {"kind": kind, "tone": args.get("tone", "friendly"),
                             "extra": {"inquiry_id": args["inquiry_id"]}})
            return _text({"draft_id": out["id"], "subject": out["subject_en"],
                          "body_en": out["body_en"],
                          "needs_confirmation": out["needs_confirmation"]},
                         note="草稿仅供人工核对后自行发送，系统不会自动发送。")
        raise KeyError(name)

    # ------------------------------------------------------------ dispatch
    def handle(self, req: dict) -> dict | None:
        if "id" not in req:
            return None  # notification
        method = req.get("method", "")
        rid = req["id"]
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"protocolVersion": PROTOCOL_VERSION,
                               "capabilities": {"tools": {}},
                               "serverInfo": SERVER_INFO}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params") or {}
            try:
                result = self._tool_call(params["name"], params.get("arguments") or {})
                return {"jsonrpc": "2.0", "id": rid, "result": result}
            except KeyError:
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"未知工具 {params.get('name')}"}],
                    "isError": True}}
            except Exception as exc:  # noqa: BLE001 — tool errors go back to the model
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": str(exc)}], "isError": True}}
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"unknown method {method}"}}


def main() -> int:
    token = os.environ.get("TRADESENSE_MCP_TOKEN", "")
    if not token:
        print("需要 TRADESENSE_MCP_TOKEN（登录接口返回的 access_token）", file=sys.stderr)
        return 1
    handler = MCPHandler(token=token)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handler.handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
