# LIVE-006B JOBS / ASR registry 变更单

作者 /root/eng_live002；状态 ready_for_review，未自批。工作副本 `.worktrees/live-006b-jobs`、分支 `feat/LIVE-006B-jobs`，任务base `74df3b1`。

依赖CFG作者提交4cf7fb0、ddc64db、309a3f6、8605455（低层配置敏感信息校验修复），本分支cherry-pick对应07d9cce、2833088、3b6579c、b8d23b1。这些共享配置成果由CFG独立拥有；作者自己的提交只包含media_jobs/media_operator/media_configuration、asr/factory与导出、两项测试文件、media-jobs文档和本报告。最终head随交接消息绑定本报告，避免自引用SHA。

## 行为

新--config-dir/--model-id通过统一registry取ASR；旧--config和持久v1输入显式桥接，不自动读.env、不静默迁移。v2保存完整merged公开snapshot、model选择、locator、自动/显式加载选项与可信runtime环境。执行/重试比较所有实际公开配置；密钥只执行resolve时在内存中存在，不入job/Settings/产物。factory集中构造offline或audio/transcriptions适配器，拒绝其他capability，不下载或执行仅描述型本地模型。

运行环境规则：development仅选development/test；production仅选production/staging，两者adapter均按生产安全限制。不修改core Settings的环境定义，不能通过CLI降级。开发默认自动读项目根.env；生产/staging必须显式--dotenv，解析不影响DB/MQSettings或os.environ。allow_network逐job显式，默认false。

005输入锁定、租约、partial产物落盘、已知call-intent复用、未知禁止重放均未改变。原stage API返回形状维持；ExecutionRoute临时密钥不进入配置快照。

## 作者验证

- 独立PG15470/live006b（仅runtime/live-006b/private.env配置，无旧006库操作）：test_media_jobs.py 8项 + test_media_registry_jobs.py 19项，27 passed（jobs-tests.log）。Starlette已有弃用warning1项。
- 旧兼容测试直接按旧006的payload形状调用create_job，未经过新submit，旁边.env放未注册alias也不影响旧任务；新worker执行成功且旧input_data原样保留。
- v2真实FFmpeg任务成功；partial失败后retry保留提取产物，3条已知call-intent不增加；未选用LLM参数变更也在任何调用前拒绝旧任务。
- unit覆盖根.env读取但不污染环境、credential不进payload/settings、每job授权、staging明确映射、正式降级拒绝、v1/v2/未知版本分支、locator重载。
- 取CFG最终8605455低层敏感信息校验更新后，19项无DB回归再通过（jobs-final-unit.log）；该依赖没有新增任何执行适配器。
- 测试产物在runtime/live-006b/pytest-jobs-*；无常驻API/worker、无MQ使用。作者已明确交还主live006b库锁。
- 无真实ASR/其他模型网络请求、无费用、无模型下载。真实PG和FFmpeg不代表供应商质量验收。

Ruff、staged diff --check、范围门禁结果随最终提交交接。业务源码小于300行，新增配置桥接139行；测试按真实任务与配置/工厂边界拆分，无500行巨型文件。

## 风险与回滚

无DB迁移；回滚代码时需保留v2任务兼容支持，旧版本不认识v2应停止这些任务而非篡改snapshot成v1。不能删已持久任务或产物。配置变化会使旧任务明确失败；重新提交新配置需要新的job和本job授权，不自动付费重放。

真实外部服务仍需后续明确授权和兼容性验证；本轮没有绕过既有paid-intent保护。scope内未改前端/报告生成/其他模型执行能力。正式部署、远程PR与独立QA结论均由ARC/QA另行记录。

后续边界修复：CLI与配置桥接接受config-env dev/prod，并在防降级检查前正规化为development/production；production+dev仍拒绝。新增5项alias/CLI解析回归，不涉及DB或CFG。
