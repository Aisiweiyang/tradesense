# 03 · Docker 部署

## 快速启动

```bash
docker compose up --build -d
# 前端(nginx) http://localhost:5173 → /api 反代到 backend:8000
# 后端 API    http://localhost:8001/docs
```

- 后端镜像基于 `python:3.13-slim`，启动时执行迁移；仅 `SEED_DEMO_DATA=1` 时写演示数据，设为 `0` 后通过首次初始化界面创建管理员。迁移失败会停止启动，不自动 stamp；
- 前端两阶段构建（node build → nginx 托管 SPA 并反代 `/api`）；
- 数据持久化在 named volume `backend_data`（SQLite 文件及上传目录 `/data/uploads`）；
- 两个构建上下文均有 `.dockerignore`，排除本地数据库、上传文件、凭据、依赖目录和构建缓存。

## 生产建议（PostgreSQL）

1. 为后端镜像安装 PostgreSQL 驱动 `psycopg`（当前默认依赖和镜像未包含），再打开 `docker-compose.yml` 中注释的 `db` 服务（postgres:16）；
2. 后端环境变量改为：
   `DATABASE_URL=postgresql+psycopg://tradesense:secret@db:5432/tradesense`
3. 设置强随机 `SECRET_KEY`，`SEED_DEMO_DATA=0`；
4. `docker compose up --build -d`。

PostgreSQL 路径尚未实测，需要先验证驱动、迁移和业务流程。现有自动回归及空库升级使用 SQLite。

## 环境变量传递

在项目根目录创建 `.env`（参考 `.env.example`），compose 会注入密钥、模型配置及 IMAP/WhatsApp 环境变量。正式使用必须设置独立的强随机 `SECRET_KEY` 并关闭演示种子。

## 升级

```bash
git pull
docker compose build
docker compose up -d
# 后端启动时自动 alembic upgrade head
```

## 备注

- 当前机器可执行 Compose 配置检查，但 Docker Engine 未运行，**未做容器构建或容器内运行验证**（见《14-已知限制》）；
- 容器内使用 SQLite 时请勿多副本水平扩展；需要横向扩展请切换 PostgreSQL。
