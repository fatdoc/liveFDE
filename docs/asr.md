# LIVE-006C 统一语音转写

本轮把已上传材料接入真实本地 ASR，增加腾讯文件/实时 V2 适配器，以及现有 React 设置页的登录、持久设置、上传试用和结果查询。其余页面仍是 Demo；没有启动 LIVE-007 画面分析、报告或直播平台采集。最终批准和实测证据见 `project-team/reports/LIVE-006C/`，代码存在不等于整轮验收通过。

## 入口和边界

| 接口 | 行为 |
|---|---|
| GET/PUT `/api/v1/asr/settings` | 登录工作区的偏好；PUT 检查 Origin、CSRF 和 expected_revision |
| GET `/api/v1/asr/health` | 配置、依赖和本地 worker 就绪检查；不是云端连通性或准确率测试 |
| POST `/api/v1/asr/transcriptions` | 已 finalize 材料 ID → 持久任务，返回 202 |
| GET `/api/v1/asr/transcriptions/{job_id}` | 仅当前工作区可查任务和受控结果 |
| WS `/api/v1/asr/stream` | cookie + Origin + 首条 CSRF；16kHz 单声道 s16le PCM |

统一 Python 方法为异步 `transcribe_file(path, request)`、异步生成器 `transcribe_stream(chunks, request)`、`health()`。公共契约在 `integrations/asr_gateway/contracts.py`。API 不接受密钥、任意 URL、模型目录或 socket 路径。

文件链：登记/上传/finalize → 校验归属与哈希 → 005 持久任务 → FFmpeg 规范化 WAV → gateway → 本地 Unix worker 或腾讯 → 校验结果 → 不可变 JSON 产物 → 查询。文件扩展名不能代替 FFprobe 内容校验；MP4/WAV/MP3/M4A/AAC 均需真实媒体类型匹配。

本地链：VAD → Fun-ASR-Nano → 可选 CAM++ 嵌入和文件内聚类 → 可选 emotion2vec → 可选 ct-punc。模型在专用进程中按配置加载和缓存，不在每个任务子进程重载；空闲默认 60 秒释放。安装/下载是明确的部署步骤，推理不得联网下载或上传。CPU 实测；CUDA 分支需要可用设备，auto 优先 CUDA 否则 CPU，MPS 未支持，不悄悄降级。

## 设置、授权和失败

共享模型路由沿用 LIVE-006B 的 v2 ModelRegistry，不改变已有 v1/v2 路由快照。`config/asr.example.yaml` 只是示例，不会自动启用。服务器通过 `LIVE_MODEL_CONFIG_DIR` 选择真实配置目录。默认偏好另用 `asr-policy.yaml` → `environments/<environment>.asr.yaml` → 开发/测试 `asr.local.yaml` 逐层覆盖；格式见 `config/asr-policy.example.yaml`。

尚未保存时 UI 读 YAML 默认并显示 revision 0，必须首次保存后才能试用。保存后 PostgreSQL 工作区偏好覆盖 YAML，管理员之后改默认不会暗改该工作区。当前没有重置默认接口；要改选项用设置页保存，不建议直接删数据库行。模型/策略完整快照随任务保存，恢复执行时配置漂移会阻止继续。双标签保存冲突保留草稿并要求重新读取。

云端必须同时满足 `privacy=cloud_allowed`、本次 `allow_network=true`、非空正数请求预算及金额预算；fallback 还需保存开启。保存云端偏好不是调用授权。不授予本次云权限时，即使保存了 fallback，仍只跑本地；无效音频、配置错误或未知结果不触发云回退。金额是用户授权上限声明，当前未接供应商账单核算，不能声称精确费用控制。请求次数以一次逻辑转写计，轮询不是新的识别任务。

云调用先提交 CallIntent；已知结果复用，未知结果禁止自动重放。实时音频不持久存储，断线/过期流不能重试。取消本地任务必须等 worker 确认底层推理停止；断 socket 不是停止证据，无法确认时记失败并禁止自动重试。任务子进程被杀、租约过期也不能直接重放共享 worker 请求。专用 worker 用 `job_id:attempt` 去重与取消标记；当前容量有限，满后安全拒绝，需要运维在确认全部停止后重启。

## 时间、说话人和情绪

输出包括 text、可得 language、segments、complete、elapsed_ms、来源 metadata 和 warnings。未知语言/说话人/情绪/时间保持 null 或 unavailable。

- `vad` 是实际 VAD 边界；`vad_window` 是被窗口切断后的范围，不是逐字强制对齐。
- CAM++ 给嵌入，聚类标签仅本文件/本次流内匿名，不是真实身份或长期画像。短于默认 2000ms 的片段不参与说话人聚类、不给上一人标签；这是保守工程阈值，不是官方准确率保证。
- `emotion_confidence` 对应模型的 emotion score，未经校准，不等于分类准确率；不据此推断稳定性格。
- 本地流是默认 5 秒窗口的 Nano 推理，不是 Nano 原生低延迟流式。冷启动、CPU 性能及输入等待均影响首片段时间；已返回片段不等于完整成功。
- `synthetic=false` 表示实际模型执行，不证明原始公开音频一定由真人录制。

## 腾讯实现与未完成范围

[文件识别文档](https://cloud.tencent.com/document/product/1093/37823)：CreateRecTask/DescribeTaskStatus 使用 TC3-HMAC-SHA256。当前 SourceType=1 直传规范化 WAV 上限 5,000,000 字节，约 156 秒；未配置 COS/公开 URL，因此长直播云转写尚未完成，不能将其描述为任意时长支持。

[实时 V2 文档](https://cloud.tencent.com/document/product/1093/131127)：`/asr/v2/<appid>` 使用单独的 HMAC-SHA1 签名；PCM 按 200ms 节奏发送并显式 end。公开 SDK 与文档的句子结构存在差异，适配两种形态；详见 `asr-tencent.md`。实时情绪没有可靠公开响应契约，本版明确不支持。凭证就绪检查不发实际请求。

本轮环境未提供完整腾讯 ID/key/app ID 和 smoke 请求/费用预算，因此真实文件与实时云调用均未执行；协议 mock 不能替代这一缺项。

## 部署和本地验收

轻量 API 依赖由 `services/backend/pyproject.toml` + `uv.lock` 锁定，WebSocket 服务端显式使用 wsproto。重型本地依赖/模型在独立 runtime venv，见 `asr-local.md`；worker 启动与私有 socket 规范见 `asr-worker.md`。模型缓存和媒体不进入 Git。emotion2vec 权重授权为 model-license/other，具体商用与再分发条件尚待核实；不可将代码许可当成所有权重的许可。

现有验收环境为 PG 15480、API 8196、UI 5196；私有配置在工作区 `runtime/live-006c/`。以下命令在产品 `app/` 执行，需事先完成本轮环境配置，不适用于客户部署或旧数据库：

```sh
uv sync --frozen --project services/backend
uv run --frozen --project services/backend python scripts/checks/live006c_preview.py worker
# 另一终端
uv run --frozen --project services/backend python scripts/checks/live006c_preview.py api
# 另一终端
npm --prefix frontend/web run dev -- --host 127.0.0.1
```

`LIVE_ASR_BACKGROUND_RUNNER=true` 仅开发预览；生产必须使用已有持久 dispatcher/worker，配置验证拒绝生产后台内存调度。第一次本地模型加载需要等待，不用假结果填补。新库回归和公开音频实测分开：

```sh
uv run --frozen --project services/backend python scripts/checks/live006c_acceptance.py
uv run --frozen --project services/backend python scripts/checks/live006c_smoke.py
```

前者创建独立 UUID 测试库并要求零 skip，排除 broker 专用测试；后者明确执行两次真实本地文件和一次真实本地流、保存证据且不授权云。不要重复执行模型实测来凑测试数。没有可靠双人参考分段和情绪标注时，不报告 DER/情绪准确率；单条公开普通话样本 CER 不能外推直播总体质量。
