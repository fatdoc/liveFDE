# 当前事实与任务
更新：2026-10-05，非自动监控。
已有 React Demo、CPB 审计、本轮规范/模板；尚无新 Python API 接通、迁移、真实分析闭环或平台采集。
Git：app/.git，首次提交待 LIVE-001 最终门禁；无 remote。前端已迁入 frontend/web，旧 CPB 已归档；ENG 完成搬迁，ARC/QA 正在独立验收。

| 任务 | owner | 状态 | 依赖 |
|---|---|---|---|
| LIVE-001 | ENG-01 | review | 搬迁/构建完成；ARC 浏览器与 QA 独立静态审查 |
| LIVE-002 | ENG-01 | backlog | 001 |
| LIVE-003 | ARC-01 | backlog | 001 |
| LIVE-004 | BE-01 | backlog | 002/003，拆子任务 |
| LIVE-005 | BE-01 | backlog | 004 |
| LIVE-006 | AI-01 | backlog | 002/003 |
| LIVE-007～014 | 见计划 | backlog | docs/05 |
| LIVE-015～017 | 见计划 | backlog | M5 |

待决策：远程组织/仓库/可见性；评分标准；M2 实测前的真实样本/模型配置和预算。
版本/端口/DB 隔离由 LIVE-002 探针登记；不抢占已有预览。
