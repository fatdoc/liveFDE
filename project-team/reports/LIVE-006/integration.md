# LIVE-006 集成验证

统筹 `/root`；基线 `43dc947904525abcfe2b81aa28235216a0ae281b`。配置作者519e313、媒体作者1ce1b466be333598a8f37324c97f5bd1d916d953、接线作者802dfe8fe3597f5820cced34f3a4e1c5e73db6b3各独立批准；详见同目录 config-review/media-review/jobs-review。配置已集成5fa4469，环境eb82bc0；最终组合代码649eb0759d1adf397e24f09b9ba458e612989939，独立批准树a994b27d04d219301d27ac674f909f09b1ee56d2与提交一致，PM最终验收通过。最终报告见final-review.md。

## 实际运行

工作区下执行 `uv run --offline --frozen --project app/services/backend python app/scripts/checks/live006_smoke.py`：真实FastAPI路由登录、创建主播和场次、初始化/上传/finalize MP4、关联场次；操作员CLI同事务创建job/stages/outbox；005受控handler子进程执行抽音和ASR；GET job确认两阶段成功。

最终成功结果 `runtime/live-006/integration/dc4b357a7a6d4460b4cd712d00dd2291/result.json`；首次成功结果 `f8808224a19646a09a6c17175f37f3f8/result.json` 保留。每份结果包含job/material/session ID、源SHA256、配置/fixture路径、真实WAV、manifest/转写引用及哈希。不存在客户视频与真实识别内容，仅合成图像/正弦波及预写文本。

实际输出WAV：16kHz、单声道、16-bit PCM；AAC解码样本尾有填充，主烟测时长2304ms，分3段，合成语句全局开始为0/1000/2000ms。不能把原视频2.25秒强行当解码样本时长。QA另用PCM精确2250ms音轨、500ms源偏移视频，逐字节核拼接及500–1500/1500–2500/2500–2750ms时间轴，见qa-media证据。

回归命令追加 `--regression`：**126 passed、0 failures/errors/skips**，JUnit `runtime/live-006/integration/0604ddf208934df78e221ac1025bd835/pytest.xml`，固定PG15460内专属库 `live006_suite_5b40effdbeac4985b90da0c397d9f425`、role live006。target.json为无密钥目的记录；application-db.json为另起Python进程通过正式get_settings/build_engine实查current_database/current_user。真实jobs测试在新库创建唯一job，spawn handler读取并写成功产物，不能从旧库假成功。

后端全套明确 **不收集 test_jobs_broker.py**：006没有配置broker；它属于005真实MQ验收，不能把本轮126项称为MQ端到端。其余用例均运行且0skip。`python3 -m unittest discover -s app/scripts/checks -p 'test_*.py'`：**28项通过**，包括8项006环境/目的守卫（其中FIFO、超大env和继承配置拒绝）；这些guard使用mock，不操作旧MQ。后端全源码/测试Ruff及diff检查通过。

## 失败与修复记录

前两次回归125pass/1fail，均为test_outbox_failure_and_redelivery：public中已有烟测/探针outbox被dispatcher先选中，目标测试event未被投递。首次尝试连接options.search_path被既有build_engine的statement_timeout options覆盖，隔离未生效；不把它称作通过。最终验收driver只在专属PG15460建立固定前缀+UUID的新数据库，核实际目标，继承同一数据库URL给迁移/应用/worker。保留原public数据、失败schema和两次JUnit（38f2f62c9c4c43ac9c6fcfcd39ff3f2f、414c3f341c4a49ce838e8f556286e02d），不删除证据、不改生产调度逻辑或屏蔽该用例。

独立QA发现的空白误完整、缺时间丢原话、巨大时间溢出已由作者修复：保留raw_text/unlocated/null，partial不会成功；网络adapter补25MB前置、总期限与安全未知结果。QA复跑33项媒体测试通过。实际ASR协议+真实Context的QA探针验证known缓存跨wrapper重建只请求一次，timeout未知结果没有第二次HTTP。

## 范围、风险与回退

0真实外部模型请求/费用；离线fixture和MockTransport分开标记。将来确认兼容供应商、密钥env和样本/预算后，操作员显式授权才执行真实请求。金额为声明上限，没有价格时不声称精确费用控制。未做视觉、报告、资产审核、前端接入或平台抓取。

未新增业务迁移/HTTP接口，无remote、未建远程PR或部署。回退需串行撤销006配置/媒体/注册接线提交，保留已有004/005schema及运行产物，不能靠删数据库回退。新任务停止派发后再回退，不删除已知/未知调用记录。全部工作副本仍保留供审计。

QA最终亲跑新的正式入口烟测 `runtime/live-006/integration/522d497025914348afdc128797a62e3b/result.json` 并独立核验实物；专属回归库只读核对见runtime/live-006/qa-final-db.json。PM在PM-01任务中明确批准本轮限定范围，不授权真实模型调用或启动后续功能。
