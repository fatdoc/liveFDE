# LIVE-005 本地变更单

状态：ready_for_review；作者 BE-01（任务 /root/eng_live002），独立 QA /root/qa_live002，集成负责人 ARC-01。作者不作最终批准。

## 基线与范围

- 工作副本：`/Users/docfat/Desktop/个人/project/直播体系FDE/.worktrees/live-005-be`。
- 分支：`feat/LIVE-005-jobs`；任务 base `8cc9ea5`；经 ARC 授权共享配置依赖 `bef80ef`（原提交 `cd85a6e3a3baf9b1e553856a8cecb5a7112e7db9`）。实现 head 由提交后的交接消息绑定本报告，避免自引用 SHA。
- 仅 jobs 模块、workers、0004 迁移、jobs 测试、任务卡和本报告。main router、Alembic env、共享配置、OpenAPI 集成由 ARC 串行负责。
- 无远程 PR、远程 CI 或发布。本变更实现任务执行基础，不代表已经实现直播分析或真实模型调用。

## 行为与契约

业务 service 内部调用 `create_job`，仅 flush，不 commit；调用者将业务记录、job/stages/outbox 放在同一事务。创建校验活跃 actor 与 workspace，不宣称输入版本的业务去重已经实现（将由后续分析调用者提供 fingerprint）。没有公开伪分析/任务创建接口。

`GET /api/v1/jobs/{id}`、`POST /{id}/retry`、`POST /{id}/cancel` 复用真实 Cookie、CSRF 和工作区校验。retry 需要 expected_revision/from_stage/Idempotency-Key，并发相同请求返回同一持久响应；新 attempt 不接受旧消息。progress 未知返回 null，错误只有 code/message/request_id/details 安全字段。

相对旧草案的明确实现扩展：JobOutput 增加有类型的 `attempt_history`，每次 retry 在同事务追加旧 attempt、安全错误、各阶段状态/reason/产物与完成 attempt。当前 attempt 留在主表，不丢失 retry 前失败证据。阶段产物是上限 256 KiB 的 JSON，后续媒体使用引用，不将原始模型异常/密钥存入历史。历史累计体积随 retry 次数增长，当前没有分页，后续可独立历史表/API 优化。

阶段成功和产物持久化同事务；skipped 带明确 reason，不伪造 artifact；retry 保留 succeeded 与 skipped 阶段。DB 是权威状态，Celery 不使用 result backend。

## 分发、进程和恢复

Outbox 使用 PostgreSQL 行锁/SKIP LOCKED、失败退避，RabbitMQ durable exchange/queue、persistent message、publisher confirm、mandatory routing。确认后才标 sent；确认后 DB 提交前崩溃允许重复投递，通过 attempt+lease fencing 去重。dispatcher 保留旧 `--check`，新增 `--once`/`--loop`。

Celery 使用 solo pool（并发通过多个 worker 实例），acks_late/reject_on_worker_lost。每个 handler 使用 spawn 独立进程、POSIX 进程组；父进程持续检查租约和取消，取消时 TERM/KILL + join，确认停止后才能 canceled。子进程 pipe watchdog 在父进程退出/失联时终止进程组。此实现支持 macOS/Linux POSIX，不声称 Windows 可用；handler 后代不得脱离自身进程组。

普通租约过期由 dispatcher 恢复为 queued、保留完成阶段；旧 token 不得提交。取消后 worker 丢失，sweeper 无法证明远端已停止，保守 failed `execution_stop_unconfirmed` 且不可 retry。精确停止失败分支同样使用 StopUnconfirmed，禁止误归 stage_failed 后重放。

付费调用协议在外部副作用前持久化 intent，成功结果已知时缓存复用；未知 intent 优先于取消并阻止自动重试。没有调用付费服务。未知结果与无法确认停止的手工处理 API 尚未实现，当前明确封锁重放，需后续受审计运维流程。生产 handler registry 当前为空，未注册 handler 显式失败；合成 handler 只允许显式测试开关，production 配置拒绝启用。

## 迁移与作者验证

0004_jobs → 0003_materials 为单一 head，独立冻结 DDL，不依赖未来 ORM 模型动态建表。BE 专用开发库此前已应用未发布0004，ARC授权使用 `ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt_history JSONB NOT NULL DEFAULT '[]'` 追加列，保留所有数据；其他尚未迁移的 QA/集成库直接使用最终0004，禁止照搬修改其他数据库。

真实隔离资源：`runtime/live-005/be.env`（私有不入库），PG 15450 的 BE 库/用户、RabbitMQ 5675 的 BE vhost。无常驻 API/worker。日志位于工作区 `runtime/live-005/`：

- `be-tests.log`：18 passed，包含真实 PG、真实 RabbitMQ 持久消息/确认/载荷与重复投递及配置验证；在预审 history/StopUnconfirmed 修正前执行。
- `be-tests-final.log`：修正后 jobs + config 19 passed，覆盖创建回滚、重复消息、并发幂等 retry、旧 attempt/旧 lease、未知 intent、缓存已知调用、outbox 失败、skip 保留、实际非协作子进程取消、停止失败禁止重试、attempt 历史、迁移元数据与真实 PG 一致。
- `be-cross-workspace.log`：追加实际跨工作区任务访问/取消验证（读取与取消均404），配合已有401/CSRF403。
- 一个现有 Starlette/httpx TestClient deprecation warning，非失败。

作者测试使用合成 handler，不能作为真实 ASR/视觉/模型完成证据。BE 已交还 MQ 节点锁，后续节点重启、独立进程故障与最终 SHA 验证由 ARC/QA 执行。

源文件职责检查：jobs 分为 models/service/execution/router/schemas；worker 分为 dispatcher/Celery薄入口/runner/进程边界/handler注册。业务文件均小于200行；约340行测试文件集中覆盖同一任务状态机，未混其他业务职责。

## 风险、回滚与未测

- 外部服务是否已完成调用不能通过杀本地进程撤销，intent 未知时必须人工核实；不盲目重放。
- actor/workspace 生命周期、跨任务业务去重、真实 provider、真实媒体、历史分页均非本任务实现。
- 出错回滚先停止 API写入/dispatcher/worker、备份 DB 与产物，再由 ARC 回退集成提交。0004 downgrade 会删除任务审计数据，禁止未经备份/确认在有价值数据环境执行。作者未对已用 BE 库执行破坏性 downgrade。
- 阶段 artifact 已有大小校验；未来 handler 必须只返回安全业务结构及文件引用。

实现参考：[Celery 配置](https://docs.celeryq.dev/en/stable/userguide/configuration.html)、[Celery 任务语义](https://docs.celeryq.dev/en/stable/userguide/tasks.html)、[Kombu 发布接口](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.html)。
