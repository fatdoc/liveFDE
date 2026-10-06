# LIVE-006C 组合审阅（进行中）

独立QA /root/qa_live001；固定main 1d38b6f，2026-10-06。完整源码从Git对象导出qa-final/snapshot，非实时main工作副本。

## 静态组合结论

已批准Tencent、UI、WS、IPC、LOCAL模块均已集成；两项P1（IPC提前停止ACK、LOCAL空转写完整性）修复仍存在。共享fallback仅允许明确授权及白名单操作失败，worker_stop_unconfirmed/空转写等不回退；unknown不自动重放。过期stream无原音不可重排，过期gateway需停止核验；父进程失败调用job:attempt停止确认，与IPC取消ID一致。7eda19d补父进程确认测试。

现有v1/v2示例快照在840d461与1d38b6f代码生成的JSON/hash完全一致；输出qa-final/snapshot-legacy.json与qa-snapshot-base.json。全增量git diff --check通过。

preview/runtime脚本固定工作区、仅0600私有配置、验证15480隔离数据库与存储；不部署到旧CPB或旧轮次。worker独立venv、Unix socket权限及显式模型配置，主API不承载重型模型依赖。

smoke脚本明确使用本地provider/local_only、无云授权；cloud_calls:0为脚本预设语义，并非该次网络审计计数，不能混用LOCAL作者独立socket audit0证据。建议HTTP/WS显式禁环境代理保证localhost鉴权链路不受代理变量影响，已交ARC。

quality-matrix工作副本按用户十项保留真实/模拟/未测边界，未将单样本CER等同整体准确率，无虚构DER或emotion accuracy。后续证据文档可按真实结果更新，不视为新业务功能验收。

## 验证边界

本人未下载权重或调用真实云；实际模型2file/WS联调由ARC执行，待核对证据。定向API/gateway/CloudRecorder/WS回归正运行本人独立QA PG15480库，结果随后追加。本文件当前不是整轮交付批准。

## 固定提交技术批准

1d38b6f 定向API/gateway/CloudRecorder/WS独立回归48 passed、0 skipped、98.99秒；实际PG15480本人专用live006c_qa_stream_20261006。日志qa-final/tests.log。无新增代码阻塞，批准此SHA组合技术审查；真实模型联调/全suite/PM范围验收需补证后收口，不把本48项模拟provider测试写成真实ASR质量验收。数据库/合成产物保留，测试进程已退出。

## 后端证据收口与增量批准

已只读核对以下实物（ARC执行，QA未重复推理）：

- `integration/0b93a2f82eae48d49120eba63547716b/pytest.xml`：313 tests，0 failures/errors/skipped，XML time279.633秒；日志摘要313 passed。旧失败批次保留，不用旧结果替代完整顺序复跑。
- `smoke/f0271ec3261642a592362602afcfb3df/observations.json`：两次文件任务succeeded/local/complete，墙钟60.781和18.918秒；WS事件started→partial→final→final→completed，local/complete/non-synthetic，15.331秒，首partial11.64秒且EOF前。
- smoke样本SHA256与本地public-zh-16k.wav逐字节哈希匹配。
- worker-main.log在该连续smoke时段五模型各有一次加载记录；随后19:01:21开始出现新VAD加载，不能把“该时段复用”写成整个持续运行日志永久只有五次加载。idle卸载后重载是设计行为。
- 旧smoke JSON的cloud_calls:0为常量，不是该轮网络审计；仅能结合local_only/无云授权说明没有走云provider。LOCAL作者direct烟测socket audit0是独立证据。

`feed434b80255b6498fac7683d36fa9b54791bf6`增量静态批准：smoke改cloud_policy/network_audit语义，HTTP trust_env=False、WS http_no_proxy，文档保留未测范围；未改变业务代码，不重复真实推理。后端技术审查可收口，代码基线1d38b6f + feed434；后续纯事实性报告归档可由ARC原样复制本报告，不伪造独立执行身份。

最终产品状态仍由PM收口；FE最后四条warning中文/首次rev0真实浏览器/页面上传证据另审。未验证腾讯真实云、长录音、DER/情绪准确率及完整用户十类样本，未完成客户交付部署。非阻塞文档建议：implementation-status上传格式段补M4A/AAC，当前实现已支持。

## FE warning增量 f948834 审阅

差异只含中文warning映射与作者报告，未改模型或网络交互；真实页面上传记录ui-browser-final.md明确来自FE作者，job149e4df6-9d60-4f24-b6de-b7056f50143c等待→运行→成功，刷新恢复旧任务结果保留；QA接受其证据归属，不冒称本人浏览器执行。rev0新账号浏览器未测，保留独立API/静态证据层级。

两条P2显示语义已交ARC：时间提示应同时说明VAD和切分窗口；Nano标点提示需容纳已启用ct-punc后处理。建议修为“时间戳表示语音检测区间或切分窗口的边界，不是逐字对齐时间。”及“Nano会生成原生标点；启用标点恢复时还会进一步处理。”。两行修正不需重跑模型，等待最终精确SHA复核。

FE717cb521917986965dc9b5305e7816116d206353复审通过，仅上述两句字符串修正、diffcheck通过；两项P2关闭。批准f948834+717cb52前端显示增量集成，不重复推理。等待main最终代码SHA及文件manifest确认，后续纯事实性文档收口。

## 最终代码及清单批准

最终main代码SHA `751c331e834823021db6ba85bda410e5bd1fd04a`，tree `b1f19ae8f4b3117545b22d841c8a34abf6c2c6d3`：独立git读取与声明一致。相对已批准1d38b6f仅5份文件变化，均为已审feed434及FE文案/作者报告；最终TranscriptionTrial.tsx逐字节等于已批准717cb52。

`project-team/reports/LIVE-006C/manifest.json`独立逐项核对：base840d461→最终代码SHA实际变更91文件；清单91唯一条目，无遗漏/多项；每个Git blob的字节数/SHA256全部匹配。清单指向不可变代码提交，后续closure-only文档明确不属于该清单，不要求递归自指hash。

批准上述最终代码SHA及tree。后端已通过独立48项与ARC完整313项回归、实际本地2file/WS证据已核对；前端纯文案增量获独立静态批准，ARC最终build/Sites结果按实际追加。首次rev0 GUI未验、腾讯云未验、十场景缺口和权重商用许可待核仍保持，不改写成全业务交付。后续状态/验证/manifest/本报告的原样归档属于事实性收口，可由ARC进行；若再改业务/部署代码，需重审受影响内容。
