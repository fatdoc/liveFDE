# 共享资源
本表是调度记录，不是硬隔离。
| 精确路径/资源 | owner | 任务 | 基线/开始 | 释放条件 | 状态 |
|---|---|---|---|---|---|
| app 存量目录搬迁、frontend/prototype→web、ignore/入口文件 | ENG-01 | LIVE-001 | 无首次提交 | staged 审查完成并交接 | 已释放，代码基线 1366573 |
| app/.git index/HEAD、LIVE-001 状态与评审记录 | ARC-01 | LIVE-001 | 无首次提交 | 首次提交及 worktree 验证完成 | 完成，收尾记录提交后释放 |
| localhost:5188 Demo 预览 | ARC-01 | LIVE-001 | frontend/web PID69984 | PM验收后统一安排下一任务 | 保留预览，不抢占 |
需登记锁文件/迁移head/OpenAPI/生成客户端/共同配置/端口/DB。开始认领，交接明确释放，不抢其他窗口资源。

## LIVE-002 / LIVE-003 轮次
- ENG-01：.worktrees/live-002-eng 中 services/backend、infra、scripts/checks、.github/workflows、docs/operations、LIVE-002 卡和报告独占。端口/DB/卷由探针确认，禁止碰5432/6379/5188。
- ARC-01：.worktrees/live-003-arc 中 docs/contracts、docs/13-window-collaboration.md、LIVE-003 卡和报告独占；不修改 ENG worktree。
- main 的 STATUS/access 仅统筹维护，集成串行；PM 不并写。共同 base ca9de2b；两个任务均独立提交/评审。

002/003实现worktree已交接只读保留；独立review完成，ARC负责main串行集成和收尾，完成提交后释放index独占。runtime/live-002及15432/5673/25673/8188集成烟测已完成；PG容器及数据保留，API/worker/原生MQ测试后停止。未删除worktree或用户数据；下轮重新登记后方可复用。

## LIVE-004 轮次
- 004A / be_live004a：.worktrees/live-004a-be；身份/core/main/依赖锁/0001迁移独占。
- 004B / ARC：.worktrees/live-004b-arc；streamers/sessions/0002迁移独占，A集成后认领main/env接线。
- 004C / eng_live002转岗BE-02：.worktrees/live-004c-be；materials/storage/0003迁移独占，不写main/config/env/锁。
- 004-ENG / eng_live004：.worktrees/live-004-eng；scripts检查/infra新环境/操作指南独占，branch chore/LIVE-004-ENG-environment。
- PostgreSQL live-fde-004:15440，runtime/live-004；4a/4b/4c/qa/integration独立库角色和storage。broker未配，不能把health ready当队列验证。
- QA读取指定提交，原作者不得最终自审；ARC负责串行主checkout和状态，PM不并写。

004统筹追加精确范围：.github/workflows/checks.yml（真实PG测试不允许skip）、scripts/checks/{live004_smoke,backend_integration_tests,export_openapi}.py、repository.py的004scope/材料fixture条目、docs/contracts实际OpenAPI与范围清单；均由ARC写，qa_live002独立审查。最终文档状态收尾可更新AGENTS/README/docs索引/本轮卡和报告。

LIVE-004收尾：业务代码集成a9a15d2，独立QA与PM验收通过；各作者写锁和QA数据库使用锁已释放，worktree/数据库只读保留作为审计证据。ARC在收尾文档提交后释放main index本轮独占；下轮需重新登记，不自动启动任务或复用数据库。5188与15440保留，8194测试进程已退出。

## LIVE-005 轮次
- base8cc9ea5，用户经PM授权任务队列与失败恢复，不包含006/前端/付费调用。
- BE-01 /root/eng_live002：.worktrees/live-005-be，feat/LIVE-005-jobs；jobs/workers/0004_jobs迁移/tests jobs及母卡/change.md。
- ENG-01 /root/be_live004a：.worktrees/live-005-eng，chore/LIVE-005-environment；infra/compose.live005.yml、scripts/checks/live005_environment.py及测试、docs/operations/live-005.md、reports/LIVE-005/environment.md。
- ARC-01：main串行集成；core/config.py、main.py、migrations/env.py、tests/test_job_config.py、scripts/checks/{repository,backend_integration_tests,live005_smoke,live005_scenarios}.py、docs/contracts、operations/backend-foundation.md、STATUS及本表、reports/LIVE-005收尾。
- 独立QA /root/qa_live002：指定SHA只读审查，runtime/live-005下记录与测试；不批准自己的代码。
- PG15450/project live-fde-005；MQ5675/25675/node live005@localhost；runtime/live-005/{be,qa,integration,qa_identity}.env隔离DB/role/vhost/storage。API烟测8195。旧5188/5432/6379/15432/15440不动。
- 不把合成任务处理器当视频分析；006与后续仍backlog。任务/索引/运行资源本轮结束后显式释放。
