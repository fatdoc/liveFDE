# 常驻本地 ASR worker（LIVE-006C）

文件job独立进程退出时不能保留大模型。本实现以一个显式启动的Unix socket进程持有同一个LocalASRProvider，provider内缓存成功推理后的模型。LOCAL当前cache_idle_seconds默认60秒：连续请求共享驻留模型，空闲到期卸载；异常/取消清除有疑问的模型状态。并非永久保留所有模型，也不是每次worker构造就立即load模型。

## 组件与部署

`LocalWorkerProvider(socket_path, config)` 是业务侧统一async file/stream/health客户端，仅stdlib/Pydantic契约，不导入torch/funasr，不自动启动服务或下载任何依赖/权重。服务端 `LocalWorkerServer` 一次接收一个已构造provider，串行推理；独立CLI入口 `python -m live_review.workers.local_asr_server` 才导入LOCAL及模型依赖。root负责factory接入route.worker_socket，轻量backend与模型runtime环境分离。

明确启动示例（示意，文件必须事先由管理员配置；本说明不包含秘密）：

```sh
/Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-006c/local-venv/bin/python \
  -m live_review.workers.local_asr_server \
  --config-json /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-006c/worker-config.json \
  --socket /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-006c/asr.sock \
  --storage-root /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-006c/storage
```

实际运行环境名由LOCAL/root登记；需安装本项目包或显式PYTHONPATH指向产品backend/src。config-json包含完整LocalConfig，必须绝对规范路径、当前uid持有、普通文件0600、≤16KiB，拒symlink/FIFO。socket父目录必须当前uid持有且0700，socket0600；storage-root必须已有规范绝对目录。macOS socket路径有长度限制，该正式路径UTF8长度79字节在104字节限制内。拒绝任何已存在socket/文件，不自动删除“疑似过期”socket；验证旧进程已退出后由管理员处理。正常SIGTERM/SIGINT会等推理清理、卸载模型，按inode核对仅删除自身socket。无TCP端口。

## RPC边界

每连接一个JSONL请求，最大128KiB（含换行）；最多8连接，单推理串行。请求包含op及完整配置稳定SHA256指纹；服务端匹配启动配置，不接受客户端更改路径、device或模型。file附受控storage-root内的规范WAV绝对路径与ASRRequest；校验WAV16kHz/mono/s16及声明时长。禁止路径越界、symlink、非WAV。服务端与客户端均拒allow_network=true或privacy非local_only；本组件没有云通道。

stream初始请求后使用base64 PCM帧（原始字节≤64KiB），16片有界队列、声明时长×32000字节总量限制，10秒输入idle；end/cancel与EOF分别结束/取消。客户端与服务端同时监督发送/接收，provider返回partial/final/error/completed标准事件。服务端适配到LocalConfig.stream_window_ms对应块大小；完成事件等provider生成器自然耗尽后才发送，避免EOF误取消成功缓存。超过帧、缓冲或期限直接安全失败，不自动重试。

EOF只触发server取消，不构成客户端已停止证明。新协议在所有请求终态之后追加stopped ACK；客户端取消时保持socket连接、发送cancel并最多等5秒，server只有等native线程结束、清理模型lease及串行锁后才发ACK。收到ACK后才能传播已确认取消；超时/断链/无ACK返回ASRError(worker_stop_unconfirmed, unknown=True)，不能宣称已停止。LOCAL的取消契约会等待正在运行的native线程结束、释放并清理模型lease，server再放行下一次推理。不能用取消asyncio任务来假装底层模型线程已停止。优雅退出可能等待耗时推理，没有“立即结束”的保证；不强杀线程或复用未知状态。健康检查只执行本地provider inspect，不load大模型、不检查云网络。错误来自固定code白名单，异常/文件路径/原始内容不穿透RPC；health缺socket返回worker_unavailable。

128KiB也是单结果/事件上限，超长结果安全失败；当前没有结果文件分页或自动拆分，这是明确容量限制。身份边界是操作系统同uid与目录/socket权限，不能宣称同一系统账号下不同进程相互强隔离。可信storage目录仍需管理员控制，路径检查不替代宿主机权限。

## 验证边界

专项测试使用真实Unix socket及合成provider，不加载模型、不下载、不调用云。覆盖连续请求同实例、stream事件与生成器释放、配置绑定、联网/隐私拒绝、WAV路径/symlink、取消等待清理、foreignsocket不覆盖、socket权限、超帧及shutdown卸载。另已显式启动独立合成worker进程PID18872，在两个跨进程file请求后SIGTERM，输出provider_calls=2并清socket，进程已退出。

真实LOCAL模型缓存复用、空闲卸载时延、CPU/GPU显存变化和最终factory接线，由root+LOCAL集成验收；上述合成证据不冒充真实模型性能结果。

## 外部进程监督与防迟到

父进程强杀文件job子进程时，子进程finally未必执行，必须额外调用 `await provider.cancel_and_wait(request_id)`；同步监督代码可使用 `asyncio.run(...)`。request_id统一为 `job.id:attempt`，WS为 `job.id:1`。只有方法正常返回才表示server已确认停止；异常一律worker_stop_unconfirmed且unknown=True。socket不可用也不能推断已停。

server用request_id登记active/排队/finished。cancel不存在的ID会创建tombstone并立即确认，从而阻止随后到达的同ID请求；active取消等清理、queued取消不进入模型、finished幂等确认。任何同ID再次转写都拒绝worker_request_reused；重试必须新的attempt ID。状态及tombstone限单个worker进程生命周期、最多4096条，不逐出避免迟到复活；达到上限拒绝新请求，需要明确受控重启。root持久Job状态仍必须阻止终态请求重放；此内存表不能替代跨重启的业务幂等账本。

005父进程需要在子进程停止后执行外部cancel_and_wait，确认失败写failed/execution_stop_unconfirmed或worker_stop_unconfirmed并禁retry，不能写canceled。WS清理必须aclose所有层级provider/recorder迭代器，并检查gather(return_exceptions=True)返回的停止未知错误；本次stream.py已处理自身层级，gateway/CloudRecorder共享层由root处理。新增协议要求同时升级并重启server；旧server无stopped ACK时新client安全返回stop_unconfirmed。
