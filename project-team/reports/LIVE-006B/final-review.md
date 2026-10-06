# LIVE-006B 最终组合独立 Review

Reviewer `/root/qa_live002`。**批准staged tree `e8d9d5f9289b307c65d243b61d5892c17fbfb8f8`**，基准HEAD `bccfbcfa5936465b5fd1ddae3cc5a0c09099d656`。审查前后树相同、无unstaged差异，staged diff --check通过。提交须保持此树并回传SHA供最终核对。

## 代码与范围

独立按文件字节核CFG最终a2753fb和JOBS最终7216234的生产源码、测试、共享YAML/.env.example与main完全一致。已批准低层URL凭证绕过修复、完整不可变v2快照、typed descriptor/timeout、V1桥接、dev/prod正规化、防降级等；详见qa-config/qa-jobs报告。

重新审ARC当前验收driver与文档/任务/资源，8guard预审已通过；逐文件清单与相对74df3b1实际全部变更路径一致。历史006说明明确v1/v2 dotenv不同。当前状态in_review，不提前done；007未启动。共享profile与本机差异、四环境模板、unsupported模型能力均据实说明，无P0/P1阻塞。

## QA亲跑与实物

最终默认driver亲跑退出0，结果：`runtime/live-006b/integration/8b7211c37ab449068ca0ae022c2a2e4a/result.json`。每次独立新库在15470，正式build_engine确认目的，未触旧006/005；无broker或真实模型网络。

正式v2 --config-dir与v1 --config两个operator任务经既有独立handler均成功，snapshot版本分别2/1。v2实际层叠segment_seconds从base4→development3→local2→dotenv1；max_duration dotenv12→系统10，秘密哨兵未入job。v1仍使用旧配置。

QA独立逐项校验extraction/transcript JSON长度和SHA256、完整audio SHA；WAV实际16000Hz/mono/16-bit PCM/35200samples=2200ms，两版本各三段，合成转写complete/synthetic明确，起点0/1000/2000ms。实物核对 `runtime/live-006b/integration/8b7211c37ab449068ca0ae022c2a2e4a/qa-artifact-verification.json`。本轮直接登记合成材料，未将其宣称上传HTTP回归。

QA此前独立亲跑CFG88tests、JOBS32tests（含8真实PG+24unit）与环境/门禁探针均通过；专属QA库和产物保留，模块报告注明准确SHA/测试层次。

## ARC证据复核

独立解析主回归JUnit `runtime/live-006b/integration/eedd57296f82477d98a16056cd96fffc/pytest.xml`：204 tests、0 failures/errors/skips。QA未重复同套204项；已亲跑最终driver验证组合入口。明确未收集broker-only文件，本轮不是MQ端到端。36工程checks及全项目Ruff/policy属于ARC执行证据，未冒充QA全部重跑。

## 边界与收口

无真实ASR/其他模型调用、无模型下载、无费用/中文识别质量证据。HF/Ollama/YOLO等仅声明，Registry.resolve拒执行；不存在Agent/RAG业务或前端/报告新增。金额仍声明，不是精确账单硬cap。逐任务网络授权、known缓存/unknown禁止重放保持；v1已有shape不被升级。没有业务迁移或依赖新增。

PG锁已交还ARC，保留测试库/实物，不进行清理。该批准仅代码组合审查；提交SHA核对及PM产品验收后另行纯文档收口，勿自动推进后续任务。

## 提交后独立核对

提交 `706f28ef87333718d5ce34c2ddf634fedf11a6f3` 的tree为 `e8d9d5f9289b307c65d243b61d5892c17fbfb8f8`，与批准树完全一致；HEAD指向此提交，Git工作区clean。本确认仅追加runtime，不修改产品Git。等待PM验收后另审纯文档收口。

## PM 最终范围验收（ARC登记）

PM-01任务01a10b7c-30e0-7fa3-9545-0001d85a33b3于2026-10-06明确验收通过。PM亲核706f28ef87333718d5ce34c2ddf634fedf11a6f3与批准树一致且clean，核204/36及新旧产物、报告/清单。接受分层/深合并/env/Registry/ASR迁移/旧任务兼容/ignore/扩展说明和操作报告，边界为非ASR仅声明、没有Agent/RAG业务、真实模型调用0。

PM授权仅文档收尾：保存本报告、任务和STATUS标done、资源释放、补最终文件清单；不启动下一轮或真实调用。最终收尾提交只更新这些记录，不更改批准产品代码。
