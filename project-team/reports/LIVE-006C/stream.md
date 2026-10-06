# LIVE-006C BE WebSocket 作者交接

角色交接：原 Tencent 作者 `/root/eng_live002` 接受 ARC 的 BE-WS 子任务，独占 modules/asr/stream.py、tests/test_asr_stream.py 与本报告。依赖 ARC d5544d3（本树f532c23）；没有编辑main、迁移、共享job代码、依赖锁。导出 `router`，由ARC注册。

## 接口与生命周期

`/api/v1/asr/stream`：升级前检查cookie身份及严格可信Origin/Sec-Fetch-Site；升级后10秒内提交 JSON `{type:"start",csrf_token,expected_revision,allow_network,max_requests,max_cost_usd}`。后五个业务字段复用Authorization及service.prepare的revision/workspace授权/模型快照，不接受客户端指定引擎、密钥或任意路径。重新验证身份后创建 kind=asr_stream_v1 Job及stage，并在同一事务删除其Outbox；这是连接自持的原始PCM流，无持久原音，不进入异步文件worker。

返回started(job_id,max_duration_seconds)后，客户端发送16kHz mono s16原始PCM二进制，单片≤64,000字节、非空偶数字节；总量≤服务端时间上限×32,000，上限取300秒与媒体配置较小值。输入idle10秒、32片有界队列、整体上限+30秒；支持JSON end/cancel/ping，ping响应pong，不延长音频idle。end需要已有音频，结束后仍监听cancel/disconnect；不允许跨provider fallback。

provider partial/final透传ASREvent；completed先把结果write_json、引用落JobStage并更新Job终态，成功提交后才发给客户端。缺完整性结果保留artifact但failed。心跳续租并检测API取消请求，退出取消子任务、释放lease；不能拿到lease时不伪造成功。云端使用CloudRecorder与持久CallIntent，不确定结果或云进行中断线/取消保留unknown并failed，不能标记succeeded或自动retry。max_requests=1表示一次识别，不把文件Describe轮询计为新转写；max_cost_usd是声明预算，当前没有可信单价估算/收费硬上限，不宣称金额已受控。

## 验证与资源

独立PostgreSQL：127.0.0.1:15480 / live006c_ws_dfbf8225d6ab，未使用主live006c或旧库。私有URL仅在工作区runtime/live-006c/ws/private.env（0600，不入Git）。测试使用真实PostgreSQL迁移、cookie登录、WebSocket和持久Job/CallIntent，ASR provider为明确synthetic模拟；无真实云请求、没有费用。

18项测试通过（首批15项38.19s，追加3项9.02s）：Origin/cookie/CSRF、revision/本地拒绝云授权、无预算拒绝、fallback拒绝、local/cloud持久成功、无Outbox、unknown保持、incomplete artifact、retry禁止、cancel/disconnect/idle/bytes限、云取消unknown。Ruff通过。测试平台出现已有Starlette httpx弃用提示，不是失败。日志在runtime/live-006c/ws/tests*.log。测试client/engine/连接已退出，保留独立库与合成产物供复核，未停共享PG容器。

ARC已确认需修改共享execution.recover_expired：stream无原音，进程崩溃时不可重新queued/建Outbox；应failed/stream_not_replayable，未知账本优先保留unknown。本作者依赖版本未含该共享修复，组合验收必须确认它及main路由注册。未验证真实提供商、浏览器麦克风编码、正式云计费或完整产品流程；作者不能批准自身实现，等待独立QA绑定提交SHA。

回滚：撤销本子任务提交与ARC对应router注册；无新迁移。已有stream job仍保留记录，不能恢复原音或重试。

取消增量：请求ID采用job:1；consume显式aclose，清理gather不再吞worker_stop_unconfirmed，finish对此写failed而非canceled。19项真实PG WS测试通过；fixture先保存workspace revision1，符合必须先PUT设置的规则。共享gateway/recorder的aclosing及005监督停止确认由ARC集成，不在本报告冒充已完成。
