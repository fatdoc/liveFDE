# LIVE-005 任务与恢复
- 状态：ready_for_review；owner BE-01；reviewer ARC-01；QA QA-01
- 依赖：LIVE-004
- 允许：services/backend/src/live_review/modules/jobs、workers、对应迁移/tests；跨模块接线精确路径在 ready 前列明。
- 验收：job/outbox同事务；派发重试；重复消息/幂等；租约心跳与中断恢复；阶段产物持久化才成功；失败阶段重试；取消请求与实际停止分开；错误可查询。
- 不做：盲目重放未知付费结果，API内跑长任务，PG以外另存一套权威状态。
- 交付：作者实现与真实隔离资源自检完成，见 reports/LIVE-005/change.md；待最终 head 的独立 QA/ARC review 与串行集成，尚未 done。

- 执行工作树 .worktrees/live-005-be，branch feat/LIVE-005-jobs，base8cc9ea5；owner BE-01 (/root/eng_live002)。共享core/config/main/env由ARC负责，不并写。
- 精确实现路径：modules/jobs/**、workers/**、0004_jobs.py、tests/test_jobs*.py、tests/jobs_fixture.py、本卡与reports/LIVE-005/change.md。
- 测试资源runtime/live-005/be.env，独立PG15450/MQ5675，勿碰其他库/节点；fixture仅显式开发开关启用。
