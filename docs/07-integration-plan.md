# 契约与集成草案
LIVE-003 输入，不是已实现 API。实现后的 OpenAPI 与模块 schema 为唯一可执行契约。
统一 /api/v1；真实 HTTP 状态；列表 items/total/limit/offset，limit 有上限；错误 code/message/request_id/details，无密钥堆栈。

| 接口组 | 行为 |
|---|---|
| auth/login、logout、me | Admin 会话 |
| streamers、sessions | 主播/场次 |
| materials/uploads | 创建/传输/finalize |
| materials/{id}/content | 鉴权媒体 Range |
| sessions/{id}/analysis-runs | 创建返回 202+job_id，查询历史 |
| jobs/{id}、retry、cancel | 真实状态、合法重试、协作取消 |
| sessions/{id}/transcripts、evidence | 版本原文、定位 |
| reports、revisions、exports | 单场/周报、修订、导出 |
| assets、assets/{id}/reviews | expected_revision 审核 |
| prep-plans、items | 已审版本、排序、适配稿 |
| settings/providers/status | 非敏感配置和连接状态 |

上传流式落临时盘，验证格式/大小/哈希，finalize 后登记；不能整段大视频读内存。首版不承诺断点续传，重试用幂等标识。
分析 Idempotency-Key 绑定工作区/输入版本/配置；同键异请求冲突。审核 expected_revision 条件更新，不能先读后无条件写。
媒体内容鉴权后单 Range 206/416，未授权不返回元数据。

## 内部边界
StorageProvider：受控 key 存取，不接任意磁盘路径。
ASRProvider：媒体引用→segments(id,start_ms,end_ms,text,speaker nullable)。
VisionProvider：frame_id/timestamp_ms→结构化观察+采样范围。
AnalysisProvider：证据/prompt_version→schema 校验的候选与报告，不批准资产。
CaptureAdapter（M5）：已关闭媒体+manifest→导入，不直接操作 DB。
EvidenceRef 包含 source_id/source_revision、segment_id 或 frame_id、start_ms/end_ms/page（按种类可空）；必须能解引用。原话与原文核对。
prompt/schema/model/rule/input 版本分开记录；规则未定可空。

## 任务
queued→running→succeeded/failed/canceled；取消先 cancel_requested，安全边界停止，不假定外部付费已停止。
probe/audio/asr/frames/vision/evidence/report/persist 按输入跳过无关阶段。
outbox 同事务，dispatcher 重试，worker 租约/心跳和幂等写。外部调用不占长 DB 事务。
attempt 保存错误与产物，从失败阶段恢复，不覆盖人工作品。付费超时结果未知先核对，不盲重放；消息只传 ID。

## 周报与审核
周报固化来源版本、未覆盖场次；重新生成新修订。AI 候选经 assets 服务入待审，审核后学习库可见。
备播引用固定 asset_revision_id，撤回历史提示，不自动替换文字。

## 后续采集
抖音独立解析/轮询/录制进程；视频号本地采集助手，不假设纯云替手机投屏。
manifest：platform/capture_run_id/room_ref/实际时间/hash/完整或中断状态。签名 URL/Cookie 不入普通日志。
明确完成事件或原子交接后才导入，文件大小暂时不变不是录完；导入唯一键防重，API 确认前不删源文件。
