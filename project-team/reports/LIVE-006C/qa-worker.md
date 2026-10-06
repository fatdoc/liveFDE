# LIVE-006C IPC 830a2db + 91f5629 独立审查：需修复

独立QA /root/qa_live001，2026-10-06。固定91f5629源快照qa-ipc/snapshot；main d8313bc+两IPC增量组合副本qa-ipc-combined/snapshot。非作者，不改作者/main/index。

## 已测
- 固定IPC SHA真实Unix套接字测试19/19通过（1.01秒），provider为synthetic，无模型或云。
- 额外取消窗口探针：qa-ipc/stop_probe.py，真实Unix连接，模拟provider在finally需150ms清理；服务器发送partial期间阻塞write，然后客户端取消。
- 实际输出：caller CancelledError；cleanup_finished_at_stop_ack False；cleanup_finished_later True。

## P1：stopped ACK 早于流provider清理

`local_worker/server.py` 的execute在stream分支直接async for provider.transcribe_stream；取消或断连发生于循环体write()时，未显式await生成器aclose()。executor finally先释放inference锁，handle等待executor结束后发stopped，但provider finally靠异步生成器回收稍后执行。实际探针确认取消返回时清理未完成。这违背stop ACK作为native工作停止证据的协议；真实LOCAL是否继续运行取决于其生成器实现，但协议层不能给出虚假已停止。

修复要求：对provider流使用aclosing/显式await aclose，确保finally结束后再release inference和stopped ACK；新增取消发生于partial发送期间的回归测试。已交ARC转作者，暂不批准IPC集成。

外层WebSocket consume新增显式aclose及worker_stop_unconfirmed传播方向正确；父进程cancel_and_wait/tombstone fencing仍需修复后组合复审。4096不逐出安全拒绝已明确设计。

组合副本 d8313bc+IPC 增量在QA独立PG库的WebSocket 19/19通过（44.95秒），日志qa-ipc-combined/tests.log；该通过不能抵消以上独立新增探针发现的P1。

## P1修复复审：批准模块集成

固定4964a0b2144195cddf5119b1badd33bc9b58e9ae新增aclosing在provider生成器关闭后才释放串行锁。独立运行原失败stop_probe.py输出cleanup_finished_at_stop_ack=True、later=True；20项Unix测试全部通过1.04秒，新增partial write取消回归覆盖原窗口。批准830a2db+91f5629+4964a0b模块集成；不重复集成共享同步提交e6cb912。LOCAL native真实取消仍属最终组合范围。
