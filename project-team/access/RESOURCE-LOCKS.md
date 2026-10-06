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

LIVE-005统筹补充测试入口守卫：scripts/checks/test_backend_integration_tests.py由ARC编写，QA独立审查；pytest启动前同时限定PG与MQ/vhost，当前本地整套仅允许live-005/qa.env，CI仍使用独立live002端点，不允许新005套件迁移旧004库。

LIVE-005收尾：业务与统筹集成8a34b5f独立QA/PM验收通过；BE/ENG/QA运行锁已交还，ARC完成纯文档提交后释放本轮main index锁。8个worktree保留只读审计；本轮PG15450、MQ5675及数据保留，API8195、worker/handler已退出。下轮重新登记资源，不自动启动006或复用其他库。

## LIVE-006 轮次（base43dc947）
- 用户授权抽音频/带时间戳转写；YAML为配置源，不默认vendor，不真实联网或收费。
- MEDIA /root/eng_live002：.worktrees/live-006-media，feat/LIVE-006-media；integrations/{media,asr}、test_media/test_asr、fixtures小JSON、docs/ai/media-asr.md、本卡/change.md。
- CFG /root/be_live004a：.worktrees/live-006-config，feat/LIVE-006-yaml；core/provider_config.py、pyproject/uv.lock、test_provider_config、infra/providers*.example.yaml、docs/ai/provider-configuration.md、config报告。
- ARC：main统筹，scripts/checks/{live006_environment,live006_smoke,test_live006_environment,repository}.py、infra/compose.live006.yml、docs/ai/{banana-reference,live006-acceptance}.md、实际范围/STATUS/资源及本轮报告。独立QA /root/qa_live002审查代码和实际产物，原作者不自批。
- 006本地任务测试PG15460/live-fde-006，runtime/live-006；live006主验收库/role，ARC与QA顺序交接，禁止并跑。媒体/config作者测试不需要DB。旧005 DB/MQ不动；006使用同005 runner本地执行，消息投递沿用005既有实现不重复宣称本轮MQ验收。所有生成WAV/视频/日志均在runtime/live-006，Git只放代码/小型fixture/报告。

006接线分派：BE /root/be_live004a 在 .worktrees/live-006-jobs（feat/LIVE-006-jobs）独占 workers/handlers.py、workers/media_*.py、tests/test_media_jobs.py、docs/ai/media-jobs.md；CFG完成后转入，不与ARC并写。ARC保留环境/烟测/主checkout串行集成。

接线实际文件：workers/media_{jobs,artifacts,calls,operator}.py及handlers.py、test_media_jobs.py、docs/ai/media-jobs.md。BE完成802dfe8后交还15460锁；ARC开始串行集成烟测，QA待交接后独立运行。

006回归隔离：同一专用PG15460内每次建立live006_suite_<UUID>独立数据库（owner live006），核验current_database/current_user、连接不含query；应用/worker沿用数据库名。原live006烟测与失败试验schema保留，不DROP或修改已有数据。目标名随每次target.json/JUnit登记。先前search_path方案被core.statement_timeout连接options覆盖已弃用，失败证据保留。

LIVE-006收尾：代码649eb07独立QA与PM最终验收通过；CFG/MEDIA/JOBS/QA均已交还写锁和15460数据库使用权，3个本轮worktree只读保留，PG15460及所有本轮实物/回归库保留。无本轮worker/FFmpeg常驻；ARC完成纯文档收尾提交后释放main index独占。下一轮需重新登记资源，不自动启动007或真实模型调用。

## LIVE-006B（base74df3b1）

CFG /root/be_live004a 独占 .worktrees/live-006b-config 的core/model_config、model_registry、config/共享YAML、.env.example及所属测试/文档。BE /root/eng_live002 独占 .worktrees/live-006b-jobs 的media_configuration/media_jobs/media_operator与ASR factory及所属测试/文档。主checkout仅ARC串行门禁/.gitignore/目录/报告/集成；QA独立只读指定SHA。运行产物runtime/live-006b，不读取真实秘密，不复用旧006业务库。独立测试库/进程资源稍后登记明确目标；当前作者仅合成文件/unit测试。

006B运行资源：新PG15470 / compose live-fde-006b / runtime/live-006b，role/database live006b。回归每次创建live006b_suite_<UUID>独立库，禁止动15460/006旧记录；ARC与QA/BE串行交接数据库使用。环境脚本基于已审006 guard复用独立目标，私有env随机生成600，不读取旧模型秘密。

006B作者已交还live006b数据库使用权；QA新建live006b_qa_a29eec20dd6d4541b6015701137d2918独立库，32项验收通过后亦交还。ARC主集成仅新建live006b_suite_<UUID>库，实际库名随runtime/live-006b/integration各target.json登记。所有旧库与证据保留。
