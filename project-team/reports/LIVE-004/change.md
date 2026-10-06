# LIVE-004 本轮交付与技术验收

用户授权：拆分身份、场次、材料并完成独立验收；Admin-only，不引入未确认的老板/运营/主播RBAC。前端接线仍属012/013。

## 执行证据
| 实际执行者 | 任务与交付 | 独立审查 |
|---|---|---|
| 子代理 /root/be_live004a | 004A身份、公共基础、0001迁移；最终996b4f4 | /root/qa_live002：13项真实PG，无skip；批准 |
| 当前任务ARC-01 | 004B场次、0002迁移；d76009e，后同步A修复 | /root/qa_live003：3场景及额外边界；批准B差异 |
| 子代理 /root/eng_live002 本轮转岗BE-02 | 004C材料、0003迁移；最终f06b846（含OpenAPI修复） | /root/qa_live002：真实PG/文件/重启复验 |
| 子代理 /root/eng_live004 | 独立任务库、环境和owner门禁；37ee63b、d33ffbb | ARC：发现环境覆盖P1后修复、8项测试复核 |
| 当前任务ARC-01 | 串行集成、实际OpenAPI、真实HTTP逐级迁移验证 | /root/qa_live002：统筹代码独立复审 |

这些是本任务内实际子代理，不是新侧栏窗口，也不代表后台常驻员工。窗口仍为PM/ARC。全部工作副本、数据库、材料和测试记录在直播体系FDE内；无远程PR/外部发布/模型调用。

## 集成与真实证据
- A main f34319f；B main e1c4cb8；C main2541817；C修复main213870d；统筹代码集成 a9a15d2f3d96cedb38b0a476e847dad3dfa0c996，提交树d3f6af1bcafb2f27d1a6251fd6e4832707d0e84c与独立批准树一致。
- A/B身份到场次集成16项通过。C初次独立复验15项通过，随后修复GET/HEAD Operation ID重复并加回归，最终f06b846独立复验16项通过/0skip；最终集成全套32通过/0skip；Ruff、8项工程门禁、契约17正例/15负例通过。OpenAPI14个路径，operation IDs无重复；仅保留已知Starlette httpx弃用警告。
- 真实综合HTTP脚本使用独立live004_integration:15440：空库0001建管理员→0002创建主播/场次→0003保留已有数据；API停止/重启后同cookie可读账号和场次；合成WAV上传/finalize/重复关联、Range/HEAD/If-Range、跨工作区401/404、再次API重启原字节与SHA256一致、退出后401。
- 首次空库增量结果固定integration-upgrade-results.json（fresh_A_to_B_to_C_upgrade=true）。不是仅在最终空库执行head，也不是SQLite/Mock。
- Alembic唯一head0003_materials；实际PG alembic check显示No new upgrade operations detected。schema导出不代替运行验证。

## 边界与恢复
- 已有前端Demo不变，当前仍显示演示数据；没有声称真实页面联调、分析/报告/审核/备播或平台采集已交付。
- CLI无默认密码/公开注册；开发临时测试账号均合成。生产管理员初始化与TLS部署留交付流程。
- 原生Broker本轮未启动，/health/ready会反映未配置队列；不能以此轮PG/API通过声称队列/AI准备完成。无remote，CI仅配置和本地等价验证。
- 上传失败的临时文件保留用于恢复，自动过期清理另列后续，不自动删除原片。迁移有downgrade定义，但删除表的逆向操作不是已有数据恢复方案；生产回滚须备份/前向修复。本轮未降级或删除已有库。
- PG15440保留、Demo5188保留；8194为烟测端口，脚本结束退出API。各worktree保持用于审计复现，下轮重分资源，不混用迁移基线。

## 下一步
建议LIVE-005任务与恢复：PG权威job/outbox、派发与租约心跳、重复消息幂等、失败重试/取消/中断恢复。用户可对PM说：“继续下一轮，开发LIVE-005任务队列与失败恢复，并完成独立验收。”本句不是自动开工授权。

## 最终验收与记录归档
- QA最终原文见[final-review.md](final-review.md)，批准精确集成树；A/C末次批准已从审核者runtime原稿完整归档至各自review.md，保留初轮问题轨迹。
- PM-01任务01a10b7c-30e0-7fa3-9545-0001d85a33b3最终确认：“PM最终产品验收通过，允许LIVE-004/A/B/C在收尾标done；范围限定身份/场次/材料后端，不是前端联调或AI完成。”PM未修改共享文件，未要求重复已通过测试。
- 本次仅本地集成与产品范围验收；未发布。收尾提交只归档审核原文与更新状态，由独立QA再核对；LIVE-005保持backlog。
