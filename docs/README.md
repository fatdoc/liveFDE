# 开发规范索引
2026-10-05 统一基线，替代旧 Java/Vue 与归档模板的开发方向；计划、实现、验证分别记录。

| 文档 | 唯一职责 |
|---|---|
| [01 产品范围](01-admin-scope.md) | V1 做什么与验收 |
| [02 架构数据](02-architecture.md) | 技术栈、数据、运行组件 |
| [03 外部组件](03-open-source.md) | 来源、复用方式与状态 |
| [04 目录规范](04-directory-contract.md) | 文件归属与整理方案 |
| [05 开发计划](05-delivery-plan.md) | 里程碑、依赖、任务 |
| [06 前端规范](06-frontend-standards.md) | 保留 Demo，接真实 API |
| [07 集成契约](07-integration-plan.md) | API/任务/模型/媒体边界 |
| [08 工作流审批](08-development-workflow.md) | 谁做什么、谁批准 |
| [09 Git/Review/PR](09-git-rules.md) | 分支、提交、合并、发布 |
| [10 数字员工](10-digital-team.md) | 角色、写范围、评审 |
| [11 CPB 审计](11-cpb-media-pipeline-audit.md) | 已查明的参考实现 |
| [12 后端规范](12-backend-standards.md) | 编码、事务、迁移、测试 |
| [13 窗口协作](13-window-collaboration.md) | PM 对话入口、窗口命名、内部沟通 |
| [ADR-001](adr/001-python-react-baseline.md) | 本次选型与取代关系 |

[任务看板](../project-team/STATUS.md) · [窗口启动模板](../project-team/templates/WINDOW-START.md) · [Review 模板](../project-team/templates/REVIEW.md)
正式文档只维护本目录一份；工作区 docs 是本目录的符号链接。

[统一ASR操作与边界](asr.md) · [本地模型](asr-local.md) · [常驻worker](asr-worker.md) · [腾讯协议](asr-tencent.md) · [LIVE-006C验收](../project-team/reports/LIVE-006C/change.md)。

[统一采集操作](capture.md) · [采集独立审查与有限集成边界](../project-team/reports/LIVE-015/arc-review.md)：默认关闭，真实平台接入及安全复核待验收。

[业务契约草案](contracts/README.md) · [后端工程操作](operations/backend-foundation.md)。草案不等于已实现API；身份/场次/材料的实际范围与OpenAPI见contracts/implementation-status.md，工程和业务验证见任务报告。
