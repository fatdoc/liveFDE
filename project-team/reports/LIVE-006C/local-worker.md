# LIVE-006C LOCAL-WORKER 作者交接

工作树`.worktrees/live-006c-worker`，分支feat/LIVE-006C-worker，基线d5544d3；仅local_worker/、workers/local_asr_server.py、tests/test_local_asr_worker.py、docs/asr-worker.md及本报告。root负责factory/route.worker_socket，LOCAL负责模型缓存和取消契约；本子任务不碰这些共享文件。

实现显式常驻Unix RPC的轻量客户端与单provider服务端、私有socket/配置文件检查、config fingerprint、受控WAV路径、16片有界stream、safe errors、超时/取消/自然耗尽generator/优雅shutdown。无自动启动、TCP、模型下载或云调用。

13项真实Unix合成pytest通过；Ruff通过。另独立合成进程PID18872接收两个file请求，provider_calls=2后SIGTERM正常退出、自有socket清理。此进程仅存续于手动smoke，未声称后台已部署。运行产物在runtime/live-006c/ws/worker-synthetic.wav；临时pytest socket目录由fixture清理，现无占用socket/后台进程。正式runtime/live-006c/asr.sock父目录最初非0700导致预期拒绝，已通知root修正共享父目录权限，本任务未擅改。

模型runtime真实provider、60秒缓存卸载、真实模型推理性能、根factory接线尚需root+LOCAL组合验证；合成测试只证明RPC、同provider实例复用与取消串行边界。结果单帧最大128KiB，过大安全失败；不能宣称无限长度转写。文档docs/asr-worker.md记录部署、协议和容量限制。作者不自批，等待独立QA。

回滚：撤销本提交与root相应factory引用；没有数据库迁移。停止显式worker后模型卸载，现有原始音频保留。
