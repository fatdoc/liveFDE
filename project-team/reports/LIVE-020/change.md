# LIVE-020 变更与证据

CAP-01，任务01a11105-8328-7283-b726-8e9d34e75c36。基线a680ff7，登记8eb4684（上游98fb4b）。设计见design.md。独立审查待固定提交，作者不自批。无真实平台/手机/ASR调用或模型下载。

实现：独立原生capture executor消费现有Outbox并调用既有run_job；新增列表恢复与created_at；health给自动执行与心跳/锁就绪状态；native新建前就绪门禁，旧幂等记录可读。默认配置仍operator和disabled。执行器只消费/恢复capture_v1；共享dispatcher/execution新增可选kind筛选经ARC精确授权。

测试与失败保留：

- 首轮runtime/live-020/evidence/live020_suite_f7119d41c88a4e569c3e34508d5c65f0：24通过、22setup错误、1失败、0跳过。setup错误来自新runtime origin5199与旧测试固定5188不符；ARC已在acceptance测试专用env设置5188，实际runtime仍5199。失败为旧synthetic crash注入进程冷启动晚于2s stall，先报stream_stalled；测试现在同步确认注入崩溃后返回Popen，生产stall时限不变。原证据保留，不将这轮称通过。
- 后续结果待固定代码验证后追加。

新测试区分：原生执行器SIGTERM/SIGKILL用真实独立Python执行器、既有handler子进程和合成receiver，检查PID退出；浏览器队列到合成音视频测试使用真实FFmpeg/材料导入，但为注入本地普通来源将handler调用留在测试进程，不以此冒充真实平台或完整子进程联调。既有HLS播放测试与纯解析拒绝断言不等于端到端出站隔离复核。

运行资源由ARC LIVE-022所有：PG15500、API8199、UI5199、DLNA8200、runtime/live-020。CAP测试套件自动建立全新隔离库；未修改旧15490/15480业务库。临时复制的live020环境脚本不属于CAP提交，ARC持有其源码与审查。

第二轮runtime/live-020/evidence/live020_suite_96bae581fe8d459e9237b28c9edc90fa：46通过、1失败、0错误/跳过。native真实SIGTERM/SIGKILL接收进程清理、自动run_job导入、busy/draining/互斥、普通合成FFmpeg闭环均通过。唯一失败为分页测试httpx params覆盖URL query导致丢session_id；已修正测试组合参数，并对非法cursor验证具体错误码。补数据库失联心跳撤回及dispatcher异常退出释放锁测试；最终完整回归运行中，不提前声明通过。
