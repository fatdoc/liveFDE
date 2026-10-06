# LIVE-006C LOCAL-WORKER 作者交接

工作树`.worktrees/live-006c-worker`，分支feat/LIVE-006C-worker，基线d5544d3；仅local_worker/、workers/local_asr_server.py、tests/test_local_asr_worker.py、docs/asr-worker.md及本报告。root负责factory/route.worker_socket，LOCAL负责模型缓存和取消契约；本子任务不碰这些共享文件。

实现显式常驻Unix RPC的轻量客户端与单provider服务端、私有socket/配置文件检查、config fingerprint、受控WAV路径、16片有界stream、safe errors、超时/取消/自然耗尽generator/优雅shutdown。无自动启动、TCP、模型下载或云调用。

13项真实Unix合成pytest通过；Ruff通过。另独立合成进程PID18872接收两个file请求，provider_calls=2后SIGTERM正常退出、自有socket清理。此进程仅存续于手动smoke，未声称后台已部署。运行产物在runtime/live-006c/ws/worker-synthetic.wav；临时pytest socket目录由fixture清理，现无占用socket/后台进程。正式runtime/live-006c/asr.sock父目录最初非0700导致预期拒绝，已通知root修正共享父目录权限，本任务未擅改。

模型runtime真实provider、60秒缓存卸载、真实模型推理性能、根factory接线尚需root+LOCAL组合验证；合成测试只证明RPC、同provider实例复用与取消串行边界。结果单帧最大128KiB，过大安全失败；不能宣称无限长度转写。文档docs/asr-worker.md记录部署、协议和容量限制。作者不自批，等待独立QA。

回滚：撤销本提交与root相应factory引用；没有数据库迁移。停止显式worker后模型卸载，现有原始音频保留。

## 取消语义修正（本次增量）

830a2db的client close socket只能触发server清理，不能证明已停，原取消证据范围不足。本增量增加stopped ACK、5秒等待/worker_stop_unconfirmed unknown、外部cancel_and_wait(job:attempt)、迟到tombstone/重复ID拒绝。server清理ack在所有任务和模型锁结束之后；重复取消不会中断清理等待。19项Unix tests通过，覆盖file/stream本地取消、停止未确认、外部active/queued/not-connected/finished取消及迟到请求。状态最多4096条且不逐出，仅本进程有效；跨重启业务幂等由root Job保持。

同一提交含stream.py窄增量：job:1、显式aclose、传播gather内worker_stop_unconfirmed，未知停止终态failed；test fixture先持久save revision1再start。19项真实PG WS测试通过（独立原测试库，23.34s）。root还需005父进程在强杀子进程后外部cancel_and_wait，gateway/recorder层aclosing，及worker_stop_unconfirmed禁retry。未改这些共享路径，不声称它们已集成。依赖5143069在本树为e6cb912，仅用于取得现有stream文件，不重复交付。

## 独立QA P1修复

QA指出91f5629在socket写partial期间取消，provider生成器停在yield位置，普通async for退出未同步aclose，导致ACK先于provider finally。已在server execute以contextlib.aclosing包住provider stream迭代器，保持串行锁直到生成器finally清理完毕。新增真实Unix回归刻意阻塞partial写入，再取消并检查收到停止确认时cleanup已完成。

专项现20 passed（1.06s）。保留QA原失败探针与报告未改；用同一runtime/live-006c/qa-ipc/stop_probe.py只读重跑，输出cleanup_finished_at_stop_ack=True、cleanup_finished_later=True。这是作者修复证据，仍需QA对新SHA独立复审。
