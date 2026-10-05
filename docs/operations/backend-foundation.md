# LIVE-002 工程环境

范围：可启动基础包、真实 PG/RabbitMQ 开发依赖、健康探针、Celery 进程、dispatcher 预检及 Alembic 入口。本文件保留LIVE-002工程启动范围；LIVE-004已增加身份/场次/材料，实际业务范围见../contracts/implementation-status.md，LIVE-005增加outbox任务恢复；模型仍未实现。

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

LIVE-005后dispatcher --check保留依赖预检，--once/--loop实际处理PG outbox；Celery只消费任务ID/attempt，权威状态和阶段产物在PG，不使用Celery结果后端。默认无生产分析handler，完整当前操作见live-005.md及本轮验收记录。健康 readiness 检查数据库和 broker，不代表 worker/模型/业务链路已就绪；worker 用 inspect ping 单独检查。公开响应不返回 DSN/异常文本。

LIVE-002基线时Alembic为空；LIVE-004后 `upgrade head` 会创建身份/场次/材料业务表。只对登记的隔离开发库执行，当前唯一head与验收见LIVE-004报告；不得将旧空迁移说明用于判断当前数据库。

## 本地门禁
```sh
python3 scripts/checks/repository.py
python3 -m unittest discover -s scripts/checks -p 'test_*.py'
uv run --project services/backend ruff check --config services/backend/pyproject.toml services/backend scripts/checks
uv run --project services/backend pytest services/backend/tests
npm --prefix frontend/web run build
npm --prefix frontend/web run test:sites
```
提交前先精确 `git add`，再运行 `python3 scripts/checks/repository.py --task LIVE-002`，它扫描 index 和 staged 变更两端；提交后用 `--base <SHA> --task LIVE-002`。任务 scope 是显式白名单，其他任务新增由 ARC 评审登记；不是物理权限边界。凭证扫描识别文件和常见密钥格式，不等于全能密钥检测，Review 仍须检查。CI 文件是本地可复现配置，无远程运行证明。

## 数据与回滚
数据 bind mount 在工作区 runtime，不创建 Docker named volume。日志与 smoke JSON 同目录；源代码 checkout 内 .venv/node_modules 是被忽略的开发依赖，不作为运行数据提交。
只停止/移除本项目容器：`docker compose --env-file ... -f infra/compose.yaml down`，禁止 `down -v`/全局 prune/删除用户卷。数据保留，代码通过 revert 回滚。Docker 本身镜像缓存和虚拟机属于全局工具缓存。

## 本次机器的原生 RabbitMQ 验证路径
Docker Hub 下载受限，本机已有 Homebrew RabbitMQ 4.2.3；本次真实端到端基础验证使用该版本，Compose 中 RabbitMQ 4.1.5 尚未启动验证，不能称 Docker 全栈已验证。

```sh
uv run --project services/backend python scripts/checks/runtime_smoke.py --env-file /absolute/workspace/runtime/live-002/private.env --native-rabbit /opt/homebrew/opt/rabbitmq/sbin/rabbitmq-server
```

脚本限制 DSN 为 live002 用户/数据库、127.0.0.1:15432/5673，拒绝 Compose/Docker 环境覆盖和工作区外 runtime（含 symlink 逃逸）。原生节点名 live002@localhost，TCP5673/分布式25673，数据/配置/日志均在 runtime/live-002/rabbit-native；清除继承的 RabbitMQ/Erlang 变量，只结束自己创建的进程组，绝不调用全局 stop 或杀其他节点。端口已用则退出。测试后停止 API、worker、原生 MQ，PG 容器保留健康；8188 是测试过程地址而非常驻预览。

CI feature/PR 根据分支 LIVE 任务 ID、base SHA 运行 ownership（含 rename 两端）；未注册任务失败。main 仅跑全树结构检查，任务路径批准来自 feature/PR，不声称本地 main 已受远程保护。003 契约样例检查文件存在时才执行；本分支不存在，集成后由 ARC 验证。
