# LIVE-006 媒体与 ASR

实现是本地媒体提取、显式离线合成 provider 和可执行 `audio/transcriptions` 兼容协议适配器。供应商、模型、地址与密钥均不预设；本轮只使用真实 FFmpeg 和 httpx MockTransport，无外网 ASR 调用，无费用。兼容聊天接口不表示支持音频接口或 `verbose_json` 时间戳；必须核验所选模型能力。

## 入口与职责

- `integrations/media/pipeline.py:extract_audio`：本地文件→16 kHz/mono/pcm_s16le WAV→按样本拆分；不导入 ASR 配置。
- `integrations/asr/pipeline.py:transcribe`：验证媒体引用、全段预算预检、逐段 provider、全局毫秒合并。
- `asr/offline.py:OfflineFixtureProvider`：显式 enabled 且 development/test，返回标记 synthetic 的预置文本；完全不听写，production 拒绝。
- `asr/compatible.py:OpenAICompatibleASRProvider`：真实可用的 multipart POST 适配器，默认网络关闭；只在显式授权或 test MockTransport 下允许执行。
- 模型是 Pydantic frozen（嵌套 tuple/model），`result.model_dump(mode="json")` / `Extraction.model_validate(payload)` / `SegmentTranscript.model_validate(payload)` 可序列化恢复。不把文件全文放进 job JSON，接线层写完整产物，job 保存 artifact 引用与摘要。

```python
from live_review.integrations.media import extract_audio, Extraction
from live_review.integrations.asr import transcribe, OfflineFixtureProvider

extraction = extract_audio(
    source, input_root=input_root, output_root=artifact_root,
    segment_seconds=300, ffmpeg_timeout_seconds=600, ffprobe_timeout_seconds=30,
    max_duration_seconds=14400, cancel=cancel_callback,
)
provider = OfflineFixtureProvider(payload, enabled=True, environment="test")
transcript = transcribe(extraction, artifact_root=artifact_root,
                       provider=provider, cancel=cancel_callback)
```

取消 callback 为无参数 callable，True 表示取消。MediaError.code=canceled 表示本地取消；子进程已停止并 wait。队列适配层需转换为 jobs.Canceled。外部请求发出后的取消不能证明供应商停止，返回 ASRUnknownCall / call_result_unknown。

## 本地媒体安全与来源

input_root 内的普通文件才可读；拒绝越界与指向根外的符号链接。源文件复制到独占 UUID 私有运行目录，计算 SHA256，前后 stat/hash 确认来源未变，处理固定副本。产物使用 artifact_root 下相对引用、大小和 SHA256。原始文件不改动，处理副本最后删除；失败仅清理本次 UUID 目录。

FFprobe/FFmpeg 参数都是数组，无 shell。输入协议只允许 file/pipe，格式白名单不允许 HLS/concat/图片序列等清单格式。工具继承 LIVE-005 handler 进程组，避免逃逸父任务取消；内部 timeout/cancel 使用 terminate→kill→wait。进程标准输出/错误使用私有临时文件且限制读取大小，错误只暴露安全 code。部署还应以低权限用户和存储挂载限制运行解析工具，不把协议白名单当作操作系统沙箱。

输出包含 source_sha256/source_size_bytes/source_duration_ms/source_audio_stream_index、16k样本数/实际时长、音轨相对容器起点偏移、工具版本和完整 WAV/分段 artifact。选择第一条音轨。coverage=`decoded_audio_track` 仅表示被选音轨成功解码；不是整个视频每个时段都有声音，也不是语音语义完整。source_integrity=`verified_snapshot` 表示输入内容校验，不表示 ASR 准确。

每段 [start_sample,end_sample) 连续不重叠，末段保留所有样本；毫秒取样本换算上整，防止亚毫秒尾段消失。全局时间=音轨起点偏移+样本位置。最多 2000 段，源文件最多16 GiB，时长受配置硬限；过限显式失败，不截断后标成功。

## ASR 协议与完整性

`ASRProvider.transcribe_segment(segment, audio_path, cancel=...) -> SegmentTranscript` 返回局部时间戳，coverage full/partial/unknown、missing_words、no_speech。pipeline 转为 source_relative 全局毫秒；缺时间戳、越界、乱序/重叠、缺词、缺段、失败、空文本均不可 complete。明确 no_speech+full+无缺词才能允许无文本完整段。现有兼容协议适配器不会从空响应自行推断 no_speech。

兼容适配器发 multipart `model`、`file`、`response_format=verbose_json`、`timestamp_granularities[]=segment`。响应 segments.start/end 秒转换为毫秒；缺字段保留缺失语义，不编造。缺失、越界、乱序时间戳及空白语句放入 `unlocated`（原text保留，start_ms/end_ms为null，附原因）；每段 `raw_text` 保留供应商顶层原文，text-only不丢原话。空白文本不能complete，显式no_speech契约才允许无文本完整段。顶层 text 与拼接 segments.text 去空白后不一致记 missing_words。保留原始文本，不将格式正规化后的文本替换为原话。

默认禁网络，真实构造必须显式 allow_network=True，密钥以 SecretStr 内存传入。只允许 HTTPS（test MockTransport 可使用合成HTTP）；follow_redirects=False、trust_env=False、不重试、不记录 token/错误体。单音频文件限制25,000,000字节（整批manifest与实际文件双检，超限不发HTTP），响应限制1 MiB；请求数与累计音频时长在整批与每段前检查。monotonic总期限在响应头、每块、读取结束与解析后检查，超限即unknown；阻塞中的单次I/O仍由httpx timeout兜底，不能声称供应商已被撤销。max_cost_usd 在缺供应商计价/usage时不能作为已验证的实际费用硬上限，授权层应评估；本轮支出为零。

timeout/网络异常/5xx/成功状态但坏JSON/溢出或不可用的巨大时间戳/响应超限为 call_result_unknown，立即停止后续段，禁止盲目重试。确定HTTP拒绝与重定向给安全失败code。LIVE-005接线必须每段在请求前 begin_paid_call、结果或确定拒绝后 finish_paid_call，未知不 finish；已知结果复用。真实网络入口和授权由队列/operator接线统一提供，本模块 CLI 不另开绕过持久intent的付费路径。

## 独立 CLI 与产物

```bash
uv run --project services/backend python -m live_review.integrations.media extract \
  --source input.mkv --input-root /absolute/runtime/input \
  --output-root /absolute/runtime/artifacts --segment-seconds 300

uv run --project services/backend python -m live_review.integrations.asr offline-transcribe \
  --manifest /absolute/runtime/artifacts/UUID/extraction.json \
  --artifact-root /absolute/runtime/artifacts \
  --fixture /absolute/runtime/offline-fixture.json \
  --enable-offline-fixture --environment test
```

extract 写 UUID/audio.wav、segment-*.wav、extraction.json。offline-transcribe 写新的 transcript-UUID.json 并打印 artifact 摘要；退出码0为完整合成协议结果、3为partial/failed、2为输入或执行错误。它是合成测试，不是真实听写。小型fixture格式为 `{"segments":{"0":{"coverage":"full","missing_words":false,"utterances":[{"text":"合成测试","start_ms":0,"end_ms":100}]}}}`。

官方依据：[FFmpeg 协议白名单](https://ffmpeg.org/ffmpeg-protocols.html)、[FFprobe](https://ffmpeg.org/ffprobe.html)、[Audio transcription API](https://platform.openai.com/docs/api-reference/audio/createTranscription)。

QA修复（2026-10-06）：未知异常使用 `from None` 抑制原始供应商异常链在常规traceback展示，避免回显敏感错误体。所有校验失败保持安全code；不将返回文本strip后替换原话。
