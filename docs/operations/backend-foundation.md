# LIVE-002 工程环境

范围：可启动基础包、真实 PG/RabbitMQ 开发依赖、健康探针、Celery 进程、dispatcher 预检及 Alembic 入口。没有业务 API、任务持久化/outbox、登录、模型或正式 schema。

## 独立启动
从产品 Git 根执行，Python 3.11、uv 0.9.26、Node 22、Docker Compose v2：

```sh
uv sync --project services/backend --locked
npm --prefix frontend/web ci
```

可先运行 `python3 scripts/checks/init_environment.py` 自动生成权限600的随机凭证文件（已存在则拒绝覆盖）。也可将私有环境文件从 `infra/.env.example` 复制至工作区 `runtime/live-002/private.env`，生成两个不同密码，权限 600。路径中的中文/空格由 Compose env-file 正常读取；不要直接 shell source 未加引号路径。
`LIVE_RUNTIME` 必须为本工作区绝对路径 `runtime/live-002`。检查 15432/5673/15672/8188 空闲；不占用已有 5432/6379/5188。Compose 项目固定 `live-fde-002`，只绑定 loopback；其他任务复制环境前须统筹重新分配项目名/端口/数据路径，不能并用本实例。

```sh
docker compose --env-file /absolute/workspace/runtime/live-002/private.env -f infra/compose.yaml up -d --wait
uv run --project services/backend python scripts/checks/runtime_smoke.py --env-file /absolute/workspace/runtime/live-002/private.env
```

smoke 启动并重启独立 API/worker，依次停止项目 PG/MQ 验证 live 200/ready 503，再恢复依赖；最后退出它启动的 API/worker，保留 PG/MQ 和数据。不要用于正在开发的共享实例。

常驻开发时由进程管理器注入 LIVE_DATABASE_URL/LIVE_BROKER_URL，然后从 services/backend 执行：

```sh
uv run uvicorn live_review.main:app --host 127.0.0.1 --port 8188
uv run celery -A live_review.workers.celery_app worker --pool=solo --hostname=live002@foundation
uv run python -m live_review.workers.dispatcher --check
uv run alembic upgrade head
```

Dispatcher 当前仅依赖预检，明确退出，不声称已经常驻分发。Celery 没有业务任务和结果后端，后续结果由业务 PostgreSQL 保存。健康 readiness 检查数据库和 broker，不代表 worker/模型/业务链路已就绪；worker 用 inspect ping 单独检查。公开响应不返回 DSN/异常文本。

Alembic 暂无 revision，`upgrade head` 验证连接和迁移基础，BE 后续创建唯一首修订；不能将空迁移作为业务表已经交付。

## 本地门禁
```sh
python3 scripts/checks/repository.py
python3 -m unittest discover -s scripts/checks -p 'test_*.py'
uv run --project services/backend ruff check services/backend scripts/checks
uv run --project services/backend pytest services/backend/tests
npm --prefix frontend/web run build
npm --prefix frontend/web run test:sites
```
提交前先精确 `git add`，再运行 `python3 scripts/checks/repository.py --task LIVE-002`，它扫描 index 和 staged 变更两端；提交后用 `--base <SHA> --task LIVE-002`。任务 scope 是显式白名单，其他任务新增由 ARC 评审登记；不是物理权限边界。凭证扫描识别文件和常见密钥格式，不等于全能密钥检测，Review 仍须检查。CI 文件是本地可复现配置，无远程运行证明。

## 数据与回滚
数据 bind mount 在工作区 runtime，不创建 Docker named volume。日志与 smoke JSON 同目录；源代码 checkout 内 .venv/node_modules 是被忽略的开发依赖，不作为运行数据提交。
只停止/移除本项目容器：`docker compose --env-file ... -f infra/compose.yaml down`，禁止 `down -v`/全局 prune/删除用户卷。数据保留，代码通过 revert 回滚。Docker 本身镜像缓存和虚拟机属于全局工具缓存。
