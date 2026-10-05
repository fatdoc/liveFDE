# CPB 媒体采集、分析与提示词审计

审计日期：2026-10-05。源码根目录：`/Users/docfat/Desktop/工作/04_研发代码/02_团队开发/CPB`，HEAD `b6a5cf3`；审计对象包括当前工作区文件，不仅是提交快照。原项目未改动，未启动服务、未调用付费模型、未读取密钥；模型名和开关均为源码默认值，不代表已验证的部署配置。以下路径相对该源码根目录。

## 结论与迁移边界

CPB 不是一个开源视频分析项目的直接套壳。它把 LiveKit、浏览器媒体接口、FFmpeg、阿里云 ASR/视觉模型、局部开源说话人模型、DeepSeek 和报告模板组合成业务流水线。AI 核心 `ai-scoring/app` 已经是 Python，可以迁移模块；Java 主要承接业务/API，Vue 承接交互，录制机器人则是 Node + Puppeteer。

本系统按用户最新决定使用 Python + React + PostgreSQL，独立部署、独立账号及存储。旧副本中“保留 Vue/Spring Boot”的说明不代表本次技术方向。此次仅完成审计与迁移设计，不表示分析功能已经在直播系统接通。

## 1. 采集：AI 证据与会议回放是两条链路

### 浏览器 AI 分析链路

入口 `frontend/user/src/components/AudioRecorder.vue:550 startRecording()`：先创建分析 session，再调用媒体录制器。

`frontend/user/src/utils/mediaRecorder.js`：

| 方法/行号 | 实际行为 |
|---|---|
| `_scanExistingTracks()` :645 | 混合本地与远端音频；选择一路视频，本地屏幕优先于摄像头，远端屏幕可覆盖，远端摄像头只补空缺。不是所有画面同时分析。 |
| `_buildCombinedStream()` :732 | 混合音频 + 所选一路视频。 |
| `startRecording()` :753 | 要求音视频轨道有效；MediaRecorder 录制，视频约 1 Mbps、音频 128 kbps，1 秒一次 chunk，暂存在浏览器内存。 |
| `_getSupportedMimeType()` :935 | 优先 WebM VP8/Opus。并不是先录 MP3。 |
| `_startRealtimeAsr()` :158 | WebAudio 混音转 16 kHz PCM16，通过 WebSocket 发往 `/api/ai/asr/stream/{session_id}`。 |
| `_startVisualFrameCapture()` :452 | 隐藏 video + canvas；起始截图、每 8 秒截图，每 2 秒检测画面变化。 |
| `_checkSceneChange()` :566 | 缩小到宽 96 像素比较 RGB 差异，阈值 0.12，场景帧间隔大于 5 秒；不是语义场景识别。 |
| `_captureVisualFrame()` :549 | JPEG，宽度上限 960，质量 0.72。 |
| `_uploadVisualFrame()` :602 | 上传画面和时间戳、clock、PTS/timebase 等到 `/api/ai/session/{session_id}/visual-frame`。 |
| `stopRecording()` :825、`_onRecordingStop()` :836 | 停实时 ASR、补尾帧、合成最终 Blob 上传；名为 `audio` 的 multipart 字段可能实际包含完整音视频 WebM。 |
| `_uploadWithProgress()` :915 | 新会话上传至 `/api/ai-score/sessions/{id}/meeting-media`，旧入口 `/api/ai/upload-audio`。 |

轨道来自 `frontend/user/src/views/MeetingRoom.vue`：`connectRoom()` :1225 连接 LiveKit；`toggleMic()` :1640、`toggleCam()` :1669 使用 getUserMedia；:1774 使用 getDisplayMedia 分享屏幕并请求系统音频。系统音频是否可用取决于浏览器与分享方式。

### 服务端会议回放链路

`MeetingRoom.vue:2040 startServerRecording()` → Java `RecordingController.java:83 startRecording()` → bot 或 Egress。

仓库 `backend/src/main/resources/application.yml:132` 默认 recording mode 为 bot，环境可覆盖。

- **Bot**：`recording-bot/src/server.js:171 startRecording()` 用 Puppeteer 打开无头 Chrome；订阅 LiveKit；`:522 drawFrame()` 将屏幕与摄像头拼版；`:569 __startCompositeRecording__()` 用 Canvas 15 fps 和混音录 WebM。停止后 `:271 remuxWebmForSeeking()` 用 FFmpeg `-c copy` 重封装，改善回放拖动，不是 AI 分析。`:312 uploadToBackend()` 上传到 `/api/recording/bot-complete`，Java 保存 MinIO 文件和录像记录。
- **Egress 备选**：`backend/src/main/java/com/orep/backend/service/LiveKitEgressService.java:43 startRoomComposite()`，speaker 布局、MP4/H264 720p30，输出到 S3/MinIO。
- 默认合成录像不是三份独立摄像头/屏幕/音频文件；代码另有独立文件上传接口与双视频分析路径，不能混为默认链路。

对核心采集目录的检索未发现抖音/视频号直播间链接解析、yt-dlp/streamlink/m3u8 拉流实现。LiveKit 负责自建 WebRTC 房间，不等于获取外部平台直播。

## 2. 停播后的 Python 分析

会话入口：`ai-scoring/app/routers/session_scoring_router.py:43 score_session()` → `services/session_pipeline_service.py:533 run_session_pipeline()` → `:614 run_pipeline_in_isolated_process()`，通过子进程运行分析，隔离本地模型崩溃。旧上传入口为 `routers/scoring_router.py:978 upload_audio()`。

主流程：`ai-scoring/app/services/pipeline_service.py:1300 run_scoring_pipeline()`。

1. **标准化音频**：`audio_service.py:15 convert_to_wav()` 使用 FFmpeg 转 16 kHz 单声道 PCM16 WAV；MP3、MP4、WebM 等是输入格式。
2. **转写**：`asr_service.py:23 transcribe_audio()` 使用 DashScope `Recognition`，默认 `fun-asr-realtime-2026-02-28`；`:107 transcribe_long_audio()` 按 300 秒分段，默认最多 3 段并发，合并时补全局时间偏移。任一段失败会报错，不能默默漏转写。模型虽叫 realtime，录后路径仍是文件 `.call()`。
3. **说话人分离**：`pipeline_service.py:982 _run_authoritative_asr()` 先云 ASR，再本地声纹分段，再对齐。`media_evidence/local_diarization.py:35 _build_sherpa_engine()` 使用 sherpa-onnx + pyannote segmentation ONNX + 3D-Speaker ERes2Net embedding。可选 3D-Speaker 视频分支及 LR-ASD 备选，不是所有部署必定执行。
4. **表达指标**：`speech_analysis_service.py:23 analyze_speech_quality()` 计算语速、停顿、口头禅和基频。用 jieba、numpy、Praat/parselmouth；语速是字数/转写发言时长，停顿主要取 ASR 段间空隙，不等于精确声学静音检测。无需 LLM 提示词。
5. **视觉分析**：`pipeline_service.py:1235 _run_video_analysis_with_session_preference()` 优先选择实时截图；按 30 秒基线与场景变化挑选，默认最多 180 张，至少 3 张进入该路径。否则 `video_analysis_service.py:505 run_analysis()` → `:65 extract_keyframes()` 从录像 FFmpeg 抽帧，`fps=1/30,scale=720:-1`。文件回退路径没有同样明确的 180 张上限。
6. **视觉模型**：`video_analysis_service.py:182 _analyze_batch()` 每批 8 张，默认最多 3 批并发，失败可逐帧重试；JPEG base64 + 视觉提示词发给 DashScope 兼容接口，源码默认 `qwen3-vl-flash`。输出每帧姿态、表情、眼神、屏幕文字/代码/图表等结构化观察。
7. **时间融合**：`fusion_service.py:232 run_fusion()` 调用按时间窗融合；主调用使用 30 秒窗。源码音频 0.6 / 视觉 0.4 是硬编码启发式，不是 LLM 提示词，也不是已认可的直播权重。
8. **证据 → 规则 → 报告**：`pipeline_service.py:314 _score_with_rule_first()` 先提取证据，再算规则账本，规则就绪时默认跳过自由打分，然后分阶段写报告。
9. **PDF**：`pipeline_service.py:2003 _generate_report()` → `report_service.py:2624 generate_report()`，ReportLab 模板排版，并非再让模型绘制 PDF。

当前主流程顶层音频分析、视频分析明确顺序执行；内部 ASR 分段和视觉批次各自可并发。不要将其描述成所有模型同时运行。

## 3. 提示词什么时候调用

以下路径均相对 `ai-scoring/app/services/`。核心提示词是 Python 字符串/工厂函数，未发现该评分主链路通过数据库 prompt registry 覆盖的证据。

| 阶段 | 提示词方法 → 调用方法 | 输入与输出 |
|---|---|---|
| 截图理解 | `video_analysis_service.py:109 _build_prompt()` → `:182 _analyze_batch()`，API :208 | 一批图片 → 每帧结构化视觉观察；默认 Qwen VL。 |
| 普通证据抽取 | `evidence_extraction_service.py:307 build_extraction_prompt()` → `:585 extract_evidence()`，API :677 | 带时间戳转写 + 视觉笔记 + 规则观测点 → claims/evidenceItems/observationEvidence/riskFlags；默认 DeepSeek。 |
| 长场次分窗 | `scoring/evidence_memory_session.py:350 _scan_prompt()` → `:43 extract_with_memory_session()` | 当前窗口文字/视觉笔记 + 已有记忆 → 更新证据记忆。 |
| 长场次证据合成 | 同文件 `:394 _synthesize_prompt()` | 记忆 + 每批 3 个观测点 → 最终 observationEvidence，引用已有 evidenceId。 |
| 报告 A | `scoring/ledger_report_service.py:606 _build_stage_a_prompt()`，调用 :172 | 权威分与事实包 → 诊断、亮点、问题、证据审计、行动方案。 |
| 报告 B1 | 同文件 `:632 _build_stage_b1_prompt()`，调用 :226 | 事实包 + A 摘要 + 评委人格 → 九评委意见。直播不必照搬。 |
| 报告 B2 | 同文件 `:656 _build_stage_b2_prompt()`，调用 :277 | 权威分 + A/B1 摘要 → 结构复盘、最终评价、证据覆盖/缺失。 |
| 旧备用自由评分 | `llm_scoring_service.py:452 score_roadshow()`、`:909 _run_core_scoring_segmented()`；prompt 工厂 `scoring_prompt_contracts.py` | 技能分 → 其余维度 → 总览 → 证据 → 评委；规则就绪时默认不走此自由评分路径。 |

原始提示词短摘录：

- 视觉：**“以下是同一场路演视频在不同时间点的截图……请对每张截图进行两部分分析：演讲者表现 + 屏幕/内容识别。”**
- 证据：**“你是OREP证据抽取器，不是评分员。只输出JSON，不输出最终总分、维度分或观测点正式分。”**
- 分窗：**“任务：只根据本窗内容更新记忆，不要重复全文。”**
- 合成：**“evidenceIds 只能使用记忆中的 evidenceId；禁止输出总分。”**

长场次触发：≥900 秒，或文本≥6000 字符，或片段≥80。目标 600 秒一窗，最多 8 窗，每窗文本预算 3500 字符；时间范围覆盖不等于逐字全文都送进模型。

通用 `llm_stage_runner.py:21 run_json_stage()` 执行模型调用、完整 JSON 解析、业务校验及阶段重试；API 位于 :71。报告最终重新锁回规则分数，模型叙述不能改总分。默认客户端 `llm_scoring_service.py:36 get_client()` 使用 OpenAI SDK 连接 DeepSeek 兼容接口；配置默认地址 `https://api.deepseek.com`，模型 `deepseek-v4-pro`。使用 OpenAI SDK 不表示使用 OpenAI 模型；这些默认值未经本次实际调用验证。

无业务生成提示词的步骤：浏览器录制、FFmpeg 转码/抽帧、ASR SDK 转写、本地说话人模型、指标计算、规则计算、时间窗融合、ReportLab 排版。

另外，`ai-scoring/server/prompts.py` 是售前/赛前生成场景，不是这里的评分 prompt。`chat_service.py:575 chat()` 当前统一走 MiMo 文本通道且 `frames=None`，画面问题使用既有摘要，不代表聊天时重新看视频。

## 4. Python + React 复刻方案

| 能力 | 建议使用 | 处理方式 |
|---|---|---|
| 录像导入 | React 上传 + FastAPI | 第一阶段入口，保留原始文件与校验值。 |
| 浏览器采集 | MediaDevices、MediaRecorder、WebAudio、Canvas | 将 CPB 媒体控制逻辑迁入 TypeScript hook/service，Vue 组件不直接复制。 |
| 自建多人直播房间 | LiveKit + 可选 Egress | 只有需要自建房间/服务端合成录制时部署；不为上传复盘强行引入。 |
| 转码与抽帧 | FFmpeg/FFprobe | Python subprocess 调用，保留毫秒级时间戳。 |
| 转写 | 阿里云 DashScope Fun-ASR | 自有账号，ASRProvider 隔离，保留分段失败和重试状态。 |
| 视觉理解 | 阿里云 Qwen VL | 自有账号，替换为直播讲解/产品演示/互动观察提示词。 |
| 多人说话人 | sherpa-onnx；需要时 3D-Speaker | 单主播 MVP 可延后视频说话人分支，明确不可确定状态。 |
| 证据和总结 | DeepSeek 兼容接口，可配置模型 | 迁移结构化 JSON、分窗记忆、证据 ID、阶段重试；重写直播业务 prompt。 |
| 任务与业务 | FastAPI + 队列 worker + PostgreSQL | session/job/stage/evidence/report/version/review/asset/preparation 自主建模。 |
| 证据文件与报告 | 独立对象存储/本地存储 + ReportLab | 保存原录像、片段、截图、提示词版本、模型配置和报告版本。 |

建议先接通：导入录像 → 转写/截图 → 可定位证据 → 单场总结 → 周总结 → 人审候选话术 → 已审核资产 → 下一场备播稿。随后补浏览器实时采集；外部平台采集单独做 CaptureAdapter。

评分仍保留产品入口，但维度未确认前显示“待配置”，提供观察与改进建议，不生成貌似客观的正式分。周总结必须引用本周多场来源，备播稿引用已审核资产；这部分是直播业务新增，不能声称 CPB 已经提供。

## 5. 迁移时需要修正的点

- 抽样截图不能证明全程动作/表情；报告必须写清覆盖范围，不根据表情推断心理状态或稳定人格。
- 文件抽帧批处理存在分钟取整的时间精度问题；使用原始毫秒时间戳、稳定 evidenceId，不从展示文本反算定位。
- 长直播需配置帧数/窗口/成本预算；长窗文本裁切可能遗漏细节，保留全文并支持证据回查与追加分析。
- CPB 报告异常捕获、清理原文件/抽帧目录的策略不适合直接继承；媒体分析完成和报告生成完成应分别记录，证据按明确保留策略保存。
- 浏览器完整录像存在内存累计与断连风险；正式长直播需要持久分块上传或服务端录制。
- 不复制竞赛时长惩罚、五维十五点、九评委、音画评分权重和固定语速阈值作为直播标准。
- 3D-Speaker 安装脚本使用 Python 3.11。项目主后端若使用较新 Python，将本地音频/视觉模型隔离到已验证兼容的 worker 环境。
- 开源项目与云服务分开管理：SDK 开源不代表模型推理免费或可本地部署；模型权重和各依赖许可需随交付组件核对。

## 官方资料

- LiveKit 自托管：https://docs.livekit.io/transport/self-hosting/
- LiveKit Egress：https://docs.livekit.io/transport/self-hosting/egress/
- DashScope Fun-ASR Python SDK：https://www.alibabacloud.com/help/en/model-studio/fun-asr-realtime-python-sdk
- sherpa-onnx 说话人分离：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html
- 3D-Speaker：https://github.com/modelscope/3D-Speaker

仓库安装脚本固定的 3D-Speaker commit 为 `065629c313eaf1a01c65c640c46d77e61e9607b4`，LR-ASD 为 `1b6dcd2d8fc2895683de6508ec6294ec47d388ca`；记录这些版本便于复现，但仍需独立安装及端到端验证。
