# 24 · MCP 工具层（把 TradeSense 接进 AI 助手）

第十一步引入：TradeSense 作为 MCP（Model Context Protocol）服务器，把确定性内核暴露给任意 MCP 能力的 AI 助手（Claude Desktop、ChatGPT 桌面版、IDE Agent 等）。

## 为什么这样是安全的

AI 助手只是**又一个客户端**：每个工具调用都走 REST API、带用户令牌——RBAC、组织隔离、审计日志、报价人工批准门禁、永不自动发送，全部照常生效。助手没有绕过任何一条安全边界，它只是替你打字。

## 启动

后端运行中（8001）：

```bash
# 令牌从登录接口取（ TradeSense 用户 demo@tradesense-demo.cn / demo1234）
export TRADESENSE_MCP_TOKEN=<access_token>
python mcp/tradesense_mcp.py
```

## Claude Desktop 配置示例

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "tradesense": {
      "command": "python",
      "args": ["<仓库路径>/mcp/tradesense_mcp.py"],
      "env": { "TRADESENSE_MCP_TOKEN": "<你的 access_token>" }
    }
  }
}
```

## 工具清单（9 个）

| 工具 | 作用 | 守护 |
| --- | --- | --- |
| ts_create_inquiry | 粘贴客户原文建询盘（自动解析） | 字段建议需人工确认 |
| ts_get_inquiry / ts_list_inquiries | 查询详情与列表 | org 隔离 |
| ts_run_match | 运行确定性产品匹配 | 硬条件淘汰带原因 |
| ts_create_quote | 生成程序计算的报价草稿 | 草稿而已，正式报价需人工批准 |
| ts_generate_reply | 生成回复草稿（10 类 × 3 语气） | 永不自动发送 |
| ts_funnel / ts_insights / ts_today | 漏斗、渠道与响应、今日待办 | 只读 |

## 实现说明

- 协议：MCP 2024-11-05，stdio 传输，每行一条 JSON-RPC；
- 零新依赖：仅用 httpx（后端已有）；协议处理与 I/O 分离（`MCPHandler.handle` 纯函数，测试直接驱动）；
- 内容块约定：说明文字在前，**最后一块始终是 JSON payload**；
- 工具错误不崩溃：以 `isError: true` 返回给模型，让它自行调整参数。

## 测试

`backend/tests/test_mcp_server.py`（7 条）：协议行为（initialize/tools/list/通知静默/未知方法 -32601）、工具映射与参数透传、错误冒泡为 isError、坏 kind 拒绝、stdio 子进程真实往返。
