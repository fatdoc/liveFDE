# 当前事实与任务
更新：2026-10-05，非自动监控。
已有 React Demo、CPB 审计、规范、Python工程基础和业务契约草案。健康端点/真实独立依赖已验；前端仍用Demo数据，LIVE-004已实现身份/场次/材料API与业务表迁移；尚无真实分析闭环或平台采集。
Git：app/.git，main 已有首次基线 13665739fb29d8aa70a9e78d32bce3d58c81bd0f；无 remote。前端 frontend/web，旧 CPB 已归档；独立技术/浏览器验收通过，试验 worktree 已验证并移除。

| 任务 | owner | 状态 | 依赖 |
|---|---|---|---|
| LIVE-001 | ENG-01 | done | 技术验收和 PM 最终核对通过；代码基线1366573，详见reports/LIVE-001/qa.md |
| LIVE-002 | ENG-01 | done | 独立审查18e721f和PM核对通过，集成19fede3；PG/原生MQ真实验证 |
| LIVE-003 | ARC-01 | done | 独立审查 b7d4efa、PM核对通过，集成26aaf4a；17正例/15负例 |
| LIVE-004 | ARC/BE | done | 独立Review和PM最终验收通过；集成a9a15d2；32真实测试/0skip，详见reports/LIVE-004 |
| LIVE-005 | BE-01 | in_progress | 004已done；用户授权，独立BE/ENG/QA，资源见access/RESOURCE-LOCKS.md |
| LIVE-006 | AI-01 | backlog | 002/003 |
| LIVE-007～014 | 见计划 | backlog | docs/05 |
| LIVE-015～017 | 见计划 | backlog | M5 |

待决策：远程组织/仓库/可见性；评分标准；M2 实测前的真实样本/模型配置和预算。
版本/端口/DB 隔离由 LIVE-002 探针登记；不抢占已有预览。

交付限制：无remote/远程CI；RabbitMQ容器模式尚未实跑（原生独立4.2.3已验）。发布前须补Compose全栈验证，见LIVE-002/follow-up.md。8188仅烟测，结束关闭；Demo5188保留。

LIVE-004环境：PG15440保留；8194仅烟测已退出。原5188 Demo仍未接后端。原LIVE-002 PG15432保留，未用于本轮业务迁移。各QA迁移基线分库，未清空/降级已有库。
