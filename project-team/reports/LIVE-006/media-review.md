# LIVE-006 MEDIA 独立审查

Reviewer `/root/qa_live002`；初审源码 `5d95545f7668a03c3769848c1bad4af8a9499682`，worktree live-006-media 初始 clean。结论暂待修复新 SHA；不能以本报告批准初审版本。

## 亲跑证据

- `uv run --offline --frozen --project services/backend pytest services/backend/tests/test_media.py services/backend/tests/test_asr.py -q`：23 passed in 4.25s，无skip。包含真实FFmpeg、坏文件/无音轨/播放列表/超时/取消/部分失败、MockTransport协议/请求及音频时长预算、未知结果不重试。
- QA独立生成3秒视频，音轨500ms起、长2250ms，经正式media CLI→offline-transcribe CLI，各退出0；输出明确synthetic，不是真听写。
- 实物 `runtime/live-006/qa-media/artifacts/3546e321178b4f56ae66c77c2b3face3/`；ffprobe独立确认pcm_s16le/16000Hz/mono/2.250000秒。完整WAV 36000 samples，三段PCM拼接与整段逐字节一致。
- 最终合成字幕全局时间为500–1500、1500–2500、2500–2750ms，保留源偏移。探测记录qa-media/ffprobe.json。
- 另用真实ffmpeg `-re -stream_loop -1`分别触发200ms超时/取消，两个实际子进程均停止且poll可得退出码。证据qa-media/process-check.json。没有模型连接/凭证读取/DB访问。

## 问题及待修复

1. 完整性阻塞：HTTP成功返回top-level text与segment.text全空白时，min_length=1与normalize相等导致最终complete；独立最小复现确认。作者须安全标partial/拒绝，非空原文保留不随意改写。
2. PM要求缺时间戳的已知原文不能无痕丢弃。初审_parse text-only为空utterances，_merge对缺时间直接continue。须保留unlocated/raw文本，时间未知不编造，也不能标完整。
3. 超大有限秒数如1e308乘1000会溢出，round抛OverflowError，未纳入ASRUnknownCall；作者需分类安全处理，避免普通失败触发盲重试。

## 静态审查与边界

FFmpeg/probe参数列表、协议/格式白名单、私有源快照/hash前后校验、产物hash和受控相对路径可见；进程继承handler组，内部停止wait。HTTP client禁止redirect/proxy环境，默认禁网、MockTransport仅test、无重试，错误体不进入公开结果。真实入口持久化intent、请求计数、快照恢复及取消整组进程待jobs/ARC集成验证。金额不是实际计费硬cap。工具临时输出文件读取受限；仍非操作系统媒体解析沙箱。

## 修复后独立批准

批准替代SHA `1ce1b466be333598a8f37324c97f5bd1d916d953`，取代初审5d95545；工作树clean。亲跑完整MEDIA/ASR：33 passed in 6.41s，无skip，Ruff/diff通过。

全部上述问题已修复：空白保留为unlocated且partial，缺失/越界/乱序时间原文保留与null，顶层raw_text保持原字符串；巨大数值归unknown且不二次调用。另核音频25,000,000字节manifest/stat双检、monotonic响应总期限、未知异常from None常规traceback脱敏测试通过。未声称取消已发请求能撤回供应商执行。

QA进一步用此前亲制实际WAV+MockTransport运行缺时间段，确认3次合成请求、partial、没有已定位utterances、原文的空格换行逐字保留、unlocated时间全null，并序列化往返一致。实物 `runtime/live-006/qa-media/qa-partial-unlocated.json`。无网络、无DB、无真实识别。

MEDIA模块范围批准；CFG/JOBS独立批准另见其报告，组合树及正式operator入口仍由最终集成审查确认。
