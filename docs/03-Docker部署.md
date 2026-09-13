# 03 · Docker 部署

## 快速启动

```bash
docker compose up --build -d
# 前端(nginx) http://localhost:5173 → /api 反代到 backend:8000
# 后端 API    http://localhost:8000/docs
```

- 后端镜像基于 `python:3.13-slim`，启动时自动执行迁移 + 演示数据种子；
- 前端两阶段构建（node build → nginx 托管 SPA 并反代 `/api`）；
- 数据持久化在 named volume `backend_data`（SQLite 文件位于 /data）。

## 生产建议（PostgreSQL）

1. 打开 `docker-compose.yml` 中注释的 `db` 服务（postgres:16）；
2. 后端环境变量改为：
   `DATABASE_URL=postgresql+psycopg://tradesense:secret@db:5432/tradesense`
3. 设置强随机 `SECRET_KEY`，`SEED_DEMO_DATA=0`；
4. `docker compose up --build -d`。

Alembic 会在启动时自动把 schema 应用到 PostgreSQL（含 `render_as_batch` 兼容）。

## 环境变量传递

在项目根目录创建 `.env`（参考 `.env.example`），compose 会注入 `SECRET_KEY`、`AI_*`、渠道凭据等。

## 升级

```bash
git pull
docker compose build
docker compose up -d
# 后端启动时自动 alembic upgrade head
```

## 备注

- 本开发环境未安装 Docker，`docker-compose.yml` 与两个 Dockerfile 已按上述结构提供并经语法审阅，但**未做容器内实机验证**（见《14-已知限制》）；
- 容器内使用 SQLite 时请勿多副本水平扩展；需要横向扩展请切换 PostgreSQL。
