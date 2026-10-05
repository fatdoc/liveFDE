# LIVE-004B 主播与场次
- 状态：review；owner ARC-01（本轮实际编写），reviewer必须独立QA，不自批。
- branch feat/LIVE-004B-sessions；worktree .worktrees/live-004b-arc；起始da128af，身份依赖base1f4595e（待A最终复审同步）。
- 写范围：modules/streamers、modules/sessions、main.py路由接线、migrations/env.py注册、0002_sessions.py、tests/test_sessions.py、本任务卡与reports/LIVE-004B。
- 依赖：004A真实身份，0001→0002；真PG live004_4b:15440，runtime/live-004/4b.env。
- 实现：主播创建列表；场次创建/详情/筛选分页/修订；未知时间null、分钟/秒精度一致、revision条件更新、同工作区FK与访问控制。
- 验收：真实API+PG并发修改一个成功一个409；跨工作区404/数据库FK拒绝、空列表、限制、日期边界、重建应用后cookie/场次仍可读。
- 不做：虚构时长/分析结果、删除/归档、前端接线、已延期dashboard/报告/学习业务。
- 迁移回滚0002会删除场次/主播，仅开发空数据可用；已有数据生产回滚须备份恢复/前向修复，不自动执行downgrade。
