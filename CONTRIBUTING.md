# 参与贡献

欢迎 issue 和 PR。开始前先读 [README](README.md) 与 [docs/14-已知限制](docs/14-已知限制.md)。

## 环境

Windows / macOS / Linux 均可。Python 3.13、Node 24：

```bash
git clone https://github.com/Aisiweiyang/tradesense.git
cd tradesense
scripts/start_dev.bat        # Windows；macOS/Linux 用 scripts/start_dev.sh
# 演示账号 demo@tradesense-demo.cn / demo1234
```

## 提交前

```bash
cd backend  && .venv/Scripts/python -m pytest -q    # 全部通过，services 覆盖率 ≥85%
cd frontend && npx tsc -b && npx vitest run
```

CI 会跑同样的检查外加 5 条 Playwright 链路，本地 `npx playwright test` 也可先跑（需前后端已启动）。

## 约定

- 需求字段解析、报价计算、单证规则等核心逻辑是**确定性代码**：改动必须带测试，且不得让 AI 直接改写这些路径的结论（AI 只提议，状态机裁决，见 docs/23）；
- 所有业务查询按 org 隔离；新表走 Alembic 迁移，与模型保持一致；
- 提交信息用一行中文主题 + 必要要点，写清楚"改了什么、为什么"；
- 新端点声明权限键（backend/app/rbac.py），新依赖需要说明理由；
- 文档在 docs/，新能力请同步更新对应文档与 docs/13 测试说明。

## 报告问题

带重现步骤、预期与实际行为、相关日志片段。安全问题请走 [SECURITY.md](SECURITY.md) 的私密渠道，不要开公开 issue。
