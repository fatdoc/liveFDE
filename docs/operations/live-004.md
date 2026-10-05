# LIVE-004 本地隔离环境

这是本轮本机验收环境，不是客户部署脚本或远程 CI 成功记录。后端身份、场次、材料的实现/测试由各子任务交付。

## 资源分配

固定工作区 `/Users/docfat/Desktop/个人/project/直播体系FDE`；产品 Git 根 `app`。
使用 `infra/compose.live004.yml`，Compose project `live-fde-004`，PostgreSQL 16.15 官方镜像以 digest 固定。
容器 `live-fde-004-postgres-1` 仅发布 `127.0.0.1:15440`。
数据 bind 到工作区 `runtime/live-004/postgres`，私有管理环境 `runtime/live-004/private.env`（600）。
初始化命令在本项目 checkout 运行：

```sh
python3 scripts/checks/live004_environment.py
```

脚本固定 project/容器/路径，拒绝工作区外 checkout、改写目标 DSN、重定向 runtime、非本项目容器，不接受任意数据库地址。重复执行保留已有密码、库和用户；已有数据库但凭证缺失或所有者不符时停止，不能 drop/recreate。新建失败后需要 ENG 核查，不可删私有 env 重试绕过保护。

| 使用方 | 数据库及登录角色 | 私有环境（相对工作区） | 材料存储（相对工作区） |
|---|---|---|---|
| BE 身份 | live004_4a | runtime/live-004/4a.env | runtime/live-004/storage-4a |
| BE 场次 | live004_4b | runtime/live-004/4b.env | runtime/live-004/storage-4b |
| BE 材料 | live004_4c | runtime/live-004/4c.env | runtime/live-004/storage-4c |
| QA 独立复验 | live004_qa | runtime/live-004/qa.env | runtime/live-004/storage-qa |
| ARC 集成 | live004_integration | runtime/live-004/integration.env | runtime/live-004/storage-integration |

每个 env 提供 `LIVE_DATABASE_URL`、`LIVE_BROKER_URL`、`LIVE_STORAGE_ROOT`。各数据库撤销 PUBLIC CONNECT，已实测自身可连接、其他任务库拒绝连接。各 owner 只迁移自己分配的数据库。
Broker 使用本机不可用的端口 1 占位，**本轮没有启动或验证队列**；需要依赖齐全的 `/ready` 不应据此宣称成功。不得用现存 RabbitMQ 凭证替代占位而伪称本轮隔离。
加载 env 使用 dotenv 或逐行切分首个 `=` 写入进程环境，路径有空格，不可直接 `source` 该 dotenv 文件。不要把 URL/密码打印到日志、报告或命令行。

保留 5432、6379、5188、15432 和既有 LIVE-002 环境。初始化不涉及它们。关闭本轮容器应由 ARC 统一协调；使用精确 project 的 `docker compose ... stop postgres` 可保留数据，禁止全局 prune、删除数据目录或 `down -v`。已有数据与凭证同为恢复所需，不纳入 Git。

## 迁移与 QA 交接

唯一顺序 `0001_identity.py → 0002_sessions.py → 0003_materials.py`，以实际代码中的 revision 为准。BE 提交实现，QA 独立执行以下真实验证并记录 SHA：

1. 在分配的空库记录初始空表，`alembic upgrade head`、`alembic heads`、`alembic current`；必须只有一个 head。
2. 增量验证在自己的独立库先升级 A，创建真实管理员/会话并保存主键，再升级 B，验证旧用户保留并创建日期未知时刻场次；最后升级 C，验证用户/场次以及完整上传原字节和 SHA256。
3. 已升级的 QA 库不自动清空。若仍需另一个空库，向 ENG 申请预先登记的新库，不能复用其他 owner 库，也不能删旧库来制造“空库”证据。
4. API 重启须核验持久化数据/会话和材料字节。共享 PostgreSQL 容器重启影响所有本轮 owner，只能 ARC 协调后执行。
5. 降级会删业务表/数据，代码审查须写出回滚边界。本轮不以对共享环境执行破坏性 downgrade 作为测试手段；必要时登记额外专用数据库。

业务测试与 OpenAPI 生成命令以子任务最终代码为准；此文不表示这些业务验证已经执行。前端 Demo 5188 不在本轮接线范围。

## 门禁

`LIVE-004A/B/C` 分别注册到明确模块、唯一迁移及测试；B/C 无依赖锁权限，C 无共享 main/config/env 权限。
`LIVE-004-ENG` 限工程辅助明确文件；`LIVE-004` 是 ARC 串行统筹共享路径。工程分支为 `chore/LIVE-004-ENG-environment`。
CI 按完整子任务 ID 匹配，未知字母后缀/任务拒绝，rename 两端都受 owner 校验。main 保留结构检查，不能替代合并前独立 Review。

```sh
python3 -m unittest discover -s scripts/checks -p 'test_*.py'
uv run --project services/backend ruff check --config services/backend/pyproject.toml scripts/checks
python3 scripts/checks/repository.py --task LIVE-004-ENG
```

最后一条检查暂存改动；提交后使用 `--base <base-sha>` 检查整个任务提交范围。未配置远程，不宣称远程 CI 或 PR 已执行。
