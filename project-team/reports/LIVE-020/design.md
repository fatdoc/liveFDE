# LIVE-020 原生采集执行与浏览器恢复设计

基线a680ff75e9509a2f879bee0106695cb49d59bd18；登记98fb4b对应本副本8eb4684。开发分支feat/LIVE-020-capture，.worktrees/LIVE-020-capture。旧015副本冻结。ARC持有15500新PG、8199 API、5199 UI、8200 DLNA及runtime/live-020，CAP不擅自启动环境。无Docker/新模型/云调用。

## 执行

独立 `python -m live_review.workers.capture_executor` 轮询原有Outbox，仅capture_v1。复用dispatch_once退避/行锁、recover_expired租约恢复、run_job与既有handler子进程。长录制在HTTP外；单执行器串行消费，忙时可持久排队。无新表/队列/迁移/依赖。

共享缝隙经ARC精确授权：recover_expired和dispatch_once仅新增可选kind过滤，不传时旧行为不变；join Job后仅锁Outbox，避免同步run_job与Job行锁自阻塞。原生模式只处理capture，不消费ASR等其他工作。

policy execution_mode默认为operator；native需明确配置，enabled仍默认false。执行器在受控root持独占文件锁、每2秒更新原子心跳并检查数据库连接与配置一致性；健康判定同时要求锁确实被占用、10秒内心跳及数据库/策略指纹匹配。仅新任务在native未就绪时返回503，既有幂等记录仍可恢复。退出/配置变化进入draining、停止接单，对当前capture设置stop_requested并等待现有受控关闭/导入。SIGKILL继承原handler管道watchdog终止子进程组；过期租约与started/manifest恢复规则不变。

心跳不是任务记录，跨主机部署不适用此原生同机模式；多机使用现有broker部署。执行器由ARC作为实际进程管理，代码存在不等于已常驻或已就绪。

## FE契约

GET /api/v1/capture/runs?session_id=UUID&limit=20&cursor=opaque → items,next_cursor。limit为1..100；created_at/id倒序keyset；workspace+场次鉴权；非法cursor422。每项是原run view加created_at，可刷新恢复并继续轮询/停止/导入。

health新增execution：mode(operator/native)、automatic_dispatch、ready、state(disabled/manual/unavailable/idle/busy/draining)、reason、heartbeat_at。视频号设备沿用providers.wechat.device_name/protocol/receiver_port/requires_phone/dependencies_ready；前端需同时检查enabled、执行器自动且ready、FFmpeg/FFprobe以及平台依赖。

开始POST新任务执行器不足返回503 capture_executor_unavailable。录完由既有capture.import自动导入；ASR仍手动，transcription_status=not_requested仅代表采集没有自动请求。state与原版保持；健康依赖就绪不代表真实平台已验。

## 验证计划与边界

覆盖分页与租户、幂等门禁、其他kind隔离、实际run_job导入、单实例、心跳过期/配置不符、draining、真实进程SIGTERM/SIGKILL及接收助手退出、本地合成音视频API队列→FFmpeg→导入。全部旧jobs回归验证两处共享参数默认行为。

不重跑旧被自动安全审核拦截的网络探针。HLS支持严格已列明标签和双引号URI；未知扩展/变量/未引号URI拒绝，不以纯解析断言或正常HLS录制代替端到端出站隔离安全结论。真实抖音、手机投屏由最终技术就绪/PM样本另验，当前仍暂停。
