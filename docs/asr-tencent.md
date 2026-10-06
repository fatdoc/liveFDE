# Tencent ASR adapter (LIVE-006C)

实现入口：`live_review.integrations.asr_gateway.tencent.TencentASRProvider`，配置 `TencentConfig`。它不依赖原 CPB，不读取旧密钥，不管理业务数据库、预算账本或任务重试。网关负责身份/预算/隐私策略与调用意图持久化；provider 再校验 `allow_network=true` 和 `privacy=cloud_allowed`，否则联网前拒绝。默认健康检查只检查配置，`network_checked=false` 不代表云服务可用。

## 两条通道

| 通道 | 输入与流程 | 明确限制 |
|---|---|---|
| 文件 | 本地 WAV → CreateRecTask → 同一 TaskId 的 DescribeTaskStatus → 结构化片段 | 16 kHz、mono、16-bit PCM，整个 WAV ≤5,000,000 bytes 且时长在 request.max_duration_seconds 内；不接 URL、不上传 COS、不自动切片 |
| 实时 V2 | PCM async iterator → WSS /asr/v2/{app_id} → 并发发送/接收 → end → final=1 | 原始16 kHz mono s16 PCM，无 WAV header；6400-byte/200ms 按1:1速度发送，短尾保留，输入等待≤5秒，整体 timeout_seconds |

文件使用官方 API 2019-06-14；TC3-HMAC-SHA256 签名绑定序列化 body。实时使用 V2 的 HMAC-SHA1/base64 签名与新 voice_id，显式 `result_mod=1`、`speaker_diarization`。只有 `16k_zh_en_2.0` 与 `16k_zh_en_speaker_2.0` 可配置为实时引擎，请求说话人标签需后者。文件默认引擎由配置显式传入，不把实时 speaker 引擎名称套入文件接口。

实时参数表与官方 Python SDK 存在展示差异：协议表描述 `sentences` 直接句子对象，SDK listener/example 则读取 `sentences.sentence_list`；实现接受两者，拒绝 V1 `result` 格式。`result_mod=1` 与 `speaker_diarization` 的依据是 SDK `_create_query_arr`。固定审计版本为 `d362182909aaf25f95cd93449c4aeae8e0b449bf`（2026-10-06读取），不是对未来 master 的假设。

## 配置与结果

`TencentConfig` 必填 `secret_id`、`secret_key`、`engine_file`、`engine_stream`；实时还需 `app_id`。凭证使用 SecretStr 且从配置 dump/repr 排除。超时参数：`timeout_seconds=120`、`io_timeout_seconds=10`、`poll_interval_seconds=1`、`max_poll_requests=120`。语言由引擎决定，request.language 只接受 auto；不承诺自动识别所有语言。实时情绪和实时关闭标点控制明确拒绝，文件情绪仅限已列支持引擎且可能额外收费，只有显式 emotion=true 才开启。

每条 segment 保留 provider 时间戳；越界/缺失为 null。speaker_id 是该次识别的编号，-1/缺失为 null，speaker_name 永远不补真实姓名。没有声纹注册/跨会话身份对齐。没有官方置信度则 confidence 与 emotion_confidence（对外语义 emotion_score）均为 null。多情绪标签无法对应单值时 emotion 为 null，不随意挑选。无时间戳的已知文本可保留，但 complete=false；空白、仍为partial、无片段也不能宣称完整识别。ASRResult text/language/metadata 由共享契约汇总定义。

## 失败与资源边界

HTTP 禁止自动重定向与环境代理，WSS 禁止重定向和自动重连；不记录签名URL、请求体、原文、SDK异常或密钥。文件响应上限2MiB、单条WS消息1MiB、单条输入1MiB、结果累计10000片段。云请求超时/断连/无法解析/取消标记 unknown，网关应进入待核对状态，不能自动重发付费请求。轮询仅查询原 TaskId，不新建任务。明确任务失败 Status=3 与成功结果分开。

发送器失败/输入停滞会中断等待接收；退出关闭 socket，取消并回收发送/接收任务。同步连接建立不可直接取消：取消时等待受 socket timeout 约束的连接返回后关闭，最坏需要 io_timeout_seconds（同时不超过配置总时长的连接超时），不能宣称瞬间终止线程。运行环境必须安装 root 管理锁定版本的 websocket-client，只有获准的实时调用才延迟导入。

## 官方依据

- [实时 V2 协议](https://cloud.tencent.com/document/product/1093/131127)
- [固定版本 Python V2 SDK](https://github.com/TencentCloud/tencentcloud-speech-sdk-python/blob/d362182909aaf25f95cd93449c4aeae8e0b449bf/asr/realtime_recognizer_v2.py)：listener 行23–37、query 行162–209、result_mod 行177、speaker_diarization 行181、签名行239–245。
- [固定版本 V2 示例](https://github.com/TencentCloud/tencentcloud-speech-sdk-python/blob/d362182909aaf25f95cd93449c4aeae8e0b449bf/examples/asr/realtimev2example.py)：sentence_list 行27–38；6400字节/0.2秒发送。
- [CreateRecTask](https://cloud.tencent.com/document/product/1093/37823)、[DescribeTaskStatus](https://cloud.tencent.com/document/product/1093/37822)、[TC3签名](https://cloud.tencent.com/document/product/213/30654)。

验证使用合成 WAV、MockTransport、内存 FakeWebsocket；没有调用真实腾讯服务。真实账号权限、识别质量、地域服务可用性、实际计费和官方现场响应兼容性尚需 root 在凭证/预算完备后执行授权短样本验收。适配器通过并不代表整条网关/worker/前端链路已验收。
