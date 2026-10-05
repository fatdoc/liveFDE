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
