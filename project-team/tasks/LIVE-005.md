# LIVE-005 任务与恢复
- 状态：backlog；owner BE-01；reviewer ARC-01；QA QA-01
- 依赖：LIVE-004
- 允许：services/backend/src/live_review/modules/jobs、workers、对应迁移/tests；跨模块接线精确路径在 ready 前列明。
- 验收：job/outbox同事务；派发重试；重复消息/幂等；租约心跳与中断恢复；阶段产物持久化才成功；失败阶段重试；取消请求与实际停止分开；错误可查询。
- 不做：盲目重放未知付费结果，API内跑长任务，PG以外另存一套权威状态。
- 交付：未执行；启动前登记资源、branch/base，交付附失败注入证据。
