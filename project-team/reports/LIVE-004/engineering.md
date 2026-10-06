# LIVE-004 工程支持变更单

- Owner：子代理 `/root/eng_live004`；独立评审由 ARC 安排，作者不能批准自己。
- Base：`da128af`；分支 `chore/LIVE-004-ENG-environment`。
- worktree：工作区 `.worktrees/live-004-eng`；未合并，由 ARC 串行集成。
- 范围：新增本轮 Compose、固定资源初始化器、子任务路径门禁、工程操作文档；不写业务模块或依赖锁，不接前端、不调用模型。

## 已验证

- Docker project `live-fde-004` 的真实 PostgreSQL 16.15 容器端口 15440，官方 digest 与 LIVE-002 已验证镜像一致。
- 五个独立数据库/角色自身连接成功；逐个用同一登录角色连接其他任务数据库均被 PostgreSQL 拒绝。
- 凭证文件 600，固定 bind 位于工作区 runtime；再次执行初始化保留已有库/角色/密码且检查数据库 owner。
- 现存 LIVE-002 PostgreSQL 15432 未被修改；5432/6379/5188 未占用或停止。
- 门禁单元测试 5 项通过，包含真实跨 owner rename 拒绝、A/B/C/工程任务完整 ID 和未知 ID 拒绝、B/C锁和共享路径拒绝。
- Ruff scripts/checks 检查通过。

## 未验证/边界

本报告不声称业务 API、迁移、材料持久化或模型已经通过；它们由 A/B/C 和独立 QA 完成。本轮 broker 未启动，env 明确使用不可用端口 1；不能把存活检查当依赖齐全 readiness。未运行远程 CI。

五份独立 env 路径与迁移操作边界见 `docs/operations/live-004.md`。本轮 PG 容器仍运行并供 A/B/C/QA/集成使用，worktree 保留供审查与修复；不自动删除数据库/卷。纯工程脚本回滚可 revert 提交，运行数据不得随代码回滚删除。

## ARC Review P1 修复

ARC 对 `ac0088d` 指出：Compose 进程继承的环境变量可能覆盖已校验 env-file，导致资源目标绕过检查。修复为：在任何 Docker 调用前拒绝所有继承的 `DOCKER_*`、`COMPOSE_*`、`LIVE_RUNTIME`、`PG_PASSWORD`（空值也拒绝）；检查当前 context 是本地绝对 unix socket，随后将该 endpoint 固定到明确传给全部子进程的环境。Compose 的 runtime/password 只由校验过的私有文件写入，并拒绝文件未知字段。

新增 3 项测试（共 8 项）覆盖 20 个继承覆盖负例、5 个非本地/畸形 context 负例及子进程环境传递，确认拒绝发生在容器操作之前。Ruff 和全部 8 项测试通过。实际重复初始化成功，并比较前后六个私有 env 的 SHA256、所有本轮数据库 OID/owner，均保持不变。修复仍待 ARC 对新 SHA 复审。

## QA 身份基线隔离增量

ARC 指派：原 QA 数据库已升到场次迁移 0002，而身份 A 分支只有 0001。新增固定登记 `qa_identity`，实际创建 `live004_qa_identity` 数据库/用户，私有 env 为工作区 `runtime/live-004/qa_identity.env`，存储 `runtime/live-004/storage-qa_identity`。仅创建新增库，既有五库/凭证未改，不执行 downgrade/drop。已交接 `/root/qa_live002`，用于身份分支独立复审。QA 后续按迁移基线分配数据库，避免较新 schema 污染旧分支验证。
