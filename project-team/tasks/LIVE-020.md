# LIVE-020 浏览器采集后端执行与复核

用户2026-10-06要求继续推进到前端直接试录。Owner CAP-01任务01a11105-8328-7283-b726-8e9d34e75c36；基线a680ff75e9509a2f879bee0106695cb49d59bd18，feat/LIVE-020-capture，.worktrees/LIVE-020-capture。旧015副本只读。

浏览器提交后原生执行器复用现有Outbox/Job/run_job，单容量执行capture_v1；默认配置关闭、operator兼容。增加按场次分页恢复，health公开实际执行就绪。停止须确认进程退出与文件关闭，复用材料导入，ASR仅手动。原被自动检查中止网络探针不重试或换工具规避；可静态防御复核、纯解析拒绝断言与正常合成HLS验证。真实试录需最终就绪审查及PM统一取得来源/手机配合。

精确写范围见repository.py LIVE-020：CAP持capture模块/worker/测试、docs/capture、报告。特别委派共享execution.py recover_expired与dispatcher.py dispatch_once的可选kind过滤，默认语义保持，必须回归旧任务；handlers.py仅capture接线。其他共享文件/迁移/依赖需协调。执行器心跳须同DB/配置绑定、有TTL与独占锁，退出不得假就绪，不消费或恢复其他种类任务。

环境由ARC持有：新runtime/live-020、拟原生PG15500/API8199/UI5199，启动前核目标与端口。不操作本机Docker、旧库或模型缓存。固定SHA交非作者审查，作者不自批。
