# LIVE-003 数据与 API 契约
- 状态：backlog；owner ARC-01；reviewer BE-01 独立窗口；QA QA-01
- 依赖：LIVE-001；可先读 docs/02、07
- 允许：docs/contracts/**、本任务卡/交接；实现模块另派 BE。
- 目标：关系/唯一约束、状态机、版本冲突、API 请求响应、证据引用、上传与任务幂等、错误统一。
- 验收：所有 Demo 路由均有接口映射；周报来源/周边界、审核/备播固定版本、Range、未知时间/null明确；生成供 FE/AI 使用的契约样例。
- OpenAPI 快照在 FastAPI 实现后从代码导出，设计草案不能伪称实际运行接口。
- 不决定：正式评分权重、用户尚未确认的标准。
- 交付：未执行；branch/worktree/base/head与独立审批启动时记录。
