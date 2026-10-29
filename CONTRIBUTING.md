# 参与贡献

欢迎报告可复现的问题、改进文档和提交代码。历史优化记录保留在 [docs/17-优化日志.md](docs/17-优化日志.md)。

## 本地开发

使用 Python 3.13 和 Node.js 24。Windows 可运行 `scripts/start_dev.bat`；macOS/Linux 可运行 `bash scripts/start_dev.sh`。

手动准备环境：

```bash
cd backend
python -m venv .venv
# Windows
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/python scripts/init_db.py
.venv/Scripts/python -m uvicorn app.main:app --port 8001
# macOS/Linux 使用 .venv/bin/python
```

新终端中启动前端：

```bash
cd frontend
npm ci
npm run dev
```

无 AI 密钥也能开发和验证，保持 `AI_PROVIDER=none` 即可。默认演示账号和所有种子资料均为虚构数据。

## 提交前检查

```bash
# backend/；先安装 requirements-dev.txt
python -m pytest --cov=app/services --cov-report=term --cov-fail-under=85

# frontend/
npm test
npm run build

# 仓库根目录；新增文件应先 git add
python scripts/check_public_release.py
```

涉及页面或业务流程时，启动演示前后端后运行 `npx playwright test`。可通过 `E2E_BASE_URL`、`E2E_API_BASE`、`E2E_TOKEN` 指定测试实例和演示账号令牌。请使用一次性测试数据库；E2E 会创建询盘、报价和单证。

## 代码约定

- 保持现有 React/TypeScript 和 FastAPI/SQLAlchemy 结构；价格、硬条件判断由确定性代码执行。
- 所有业务查询和写入都须按组织隔离，并遵守固定角色权限矩阵。
- 人工锁定字段不可由规则或 AI 覆盖；正式报价必须人工批准，改价须重新审批。
- 模拟数据与真实连接状态须明确区分；未经真实验证，不宣称外部服务已连接。
- 不添加自动对外发送、自动确认合同等行为；这类变更需要单独讨论产品范围。
- 数据模型变更须提供 Alembic 迁移，并验证空库升级及已有数据保留；迁移错误应明确失败，不用 stamp 掩盖。
- 为实际缺陷补回归测试，优先覆盖可观察的行为，避免只验证实现细节。

## Issue 与 Pull Request

问题报告请包含环境、复现步骤、期望行为、实际结果及脱敏后的错误日志。界面问题可附截图。

PR 请说明解决的问题、最终行为和实际运行的验证。将改动限制在一个清晰主题内，并明确哪些外部集成尚未验证。

不要提交 `.env`、真实令牌、业务数据库、真实客户单证、上传文件、依赖目录或构建缓存。PDF 测试样本仅保留 `frontend/e2e/fixtures/` 中的虚构文件。

安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告，避免在公开 Issue 中附带可利用的细节或凭据。

贡献按仓库现有的 [AGPL-3.0](LICENSE) 许可证提供。
