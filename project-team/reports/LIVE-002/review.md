# LIVE-002 最终独立复审

日期：2026-10-05；Reviewer：/root/qa_live002。
Base：ca9de2bcd80bd224ebdc43de5ad767657e3cff90。
批准代码 Head：18e721f3c123b064104c90d94732374d6ed80063。
审阅与复测前后 worktree 干净、HEAD 未变；ENG 明确交接运行资源独占锁。

## 结论

**批准该 SHA 进入本地串行集成，限定为工程基础能力。** 初审 P1 环境隔离及 P2 ownership 门禁问题已解决，无残留阻塞代码问题。原生 RabbitMQ 路径属于 ARC 已允许的真实依赖验证替代；Compose RabbitMQ 镜像启动仍未验收，必须在交付限制保留。此批准不代表生产发布、业务后端完成或 CI 远程执行成功。

## 独立证据

在 `.worktrees/live-002-eng` 对上述 HEAD 实际运行：

- pytest：3 passed，保留 Starlette/httpx 弃用警告。
- Ruff 显式项目配置、no-cache：通过。
- policy unittest：3 passed，包含真实临时 Git 跨 owner rename 返回非零。
- repository.py --base ca9de2b --task LIVE-002：0 violations。
- GITHUB_HEAD_REF=feat/LIVE-002-foundation 与完整 base SHA 模拟 ci_policy.py：0 violations。CI 已设置 fetch-depth:0，未登记 task fail closed；main 明确仅结构校验，依赖 feature/PR ownership 检查和串行集成规则。
- 四个独立 mock 配置负例：外部 DB 端口、外部 MQ 端口、COMPOSE_PROJECT_NAME 继承覆盖、未知 env 键，均在任何 subprocess 前拒绝。代码还校验 user/db/path/password、query/fragment、Docker Unix context，runtime resolved path 必须等于工作区固定路径，关闭原 symlink 逃逸。
- **真实独立重放**：`uv run --project services/backend python scripts/checks/runtime_smoke.py --env-file ../../runtime/live-002/private.env --native-rabbit /opt/homebrew/opt/rabbitmq/sbin/rabbitmq-server` 完整退出 0。
  - Alembic upgrade head 成功；无业务 revision。
  - live200、ready200（database up、broker up）。
  - worker pong；dispatcher preflight_only 通过。
  - API 重启后 ready200；worker 重启后再次 pong。
  - 停止本任务 PG：live200、ready503(database down, broker up)；恢复后 ready200。
  - 停止本任务原生 MQ：live200、ready503(database up, broker down)；恢复后 ready200。
- 结束后独立 socket 检查 8188/5673/25673 均关闭；Docker inspect 确认 live-fde-002-postgres-1 healthy，唯一数据 bind 为工作区 runtime/live-002/postgres。没有停止、迁移或操作其他项目数据库/预览服务。

上述运行生成 `runtime/live-002/smoke-results.json`。该文件现在为 QA 独立重放结果；源码中的脱敏 smoke-results 为作者此前记录，两者结论一致。运行记录不是常驻 API 地址承诺。

## 剩余限制与集成要求

- Compose MQ4.1.5 未实跑，真实重放使用独立原生 MQ4.2.3；不将两者视作同版本镜像验收。后续客户部署前必须在目标 Compose 配置重测。
- 没有 remote；CI 仅有配置和本地等价检查，未启用真实远程门禁或分支保护。
- 未实现业务 API、持久化 jobs/outbox、鉴权、模型、媒体抓取或业务表。worker ping 不是业务任务成功，空迁移不是业务数据库验收。
- 前端源码未改；本次独立审查未重复前端构建，作者前端 build/hosting 检查记录已阅读。
- 此次未为审核修改源码或提交。集成后应复查差异和受影响检查；代码变化会使对应批准失效。QA 资源锁现归还 ARC/ENG。
