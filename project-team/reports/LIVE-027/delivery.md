# LIVE-027 真实ASR失败证据与诊断、时间戳界面

已有真实抖音片段在转写阶段失败，未产出全文和识别时间戳。本轮提交前发现已有job974e38db-d7e6-4717-820c-f2cc6747a744，保留原失败，不追加或重放模型请求。录制成功仍归LIVE-026，不等同本轮转写成功。

## 运行事实

材料41507f74-c477-4744-be5a-558ff0496480，来自run3407c23d；原MP4时长60.067秒、20,534,651字节。提取音频958123采样，16kHz、单声道、16-bit，59.8826875秒；SHA256及source引用与采集manifest匹配。音轨范围是提取证据，不是识别时间戳。QA-02独立复算原片/两WAV哈希、大小和格式一致。

只读API结果job failed/revision4，stage.reason=stage_failed，artifact/result均null。API日志显示handler_error type=ASRError后handler_stopped，本地worker同期加载VAD/Nano/标点模型；不据加载日志推断完成或准确性。原实现丢失具体安全错误码，无法从现存证据恢复本次根因。

对旧job3a7e154f及本次974e38db请求:1分别取得明确停止ACK；活跃capture/job均0。本地设置provider=local、privacy=local_only、fallback=false，health仅就绪检查、未触发网络。无本轮新录制/上传/云调用/模型下载/重试。

## 界面与诊断范围

现有材料组件显示毫秒起止、识别与时间戳来源；VAD区间不称逐词对齐。每份材料独立播放器，边界非法/元数据未就绪/材料归属未确认禁止定位。手输任务、旧存储或刷新恢复只展示；当前卡片提交并取得的job才可定位。不通过再转写来绕开限制。合成浏览器证明UI隔离，不能代替真实识别/媒体定位验收。

PM批准补齐最小安全错误码传递和日志，保留固定白名单，不记录原异常、转写原文、音频或凭证，不修改unknown/停止确认优先级。代码、独立Review、CI和部署结论在本报告完成时补齐；当前不得声称根因已修复。

## 未验与证据

真实全文、分段起止/全局单调性、source/synthetic结果字段、听核误识别和定位准确性均未验，因为本次ASR没有结果。不能用合成UI、提取manifest、另一模型输出或浏览器播放代替听核。后续真实重试须保持单次明确授权，先确认空闲/停止，不自动重放。

本地私有证据runtime/live-027/preflight.json、existing-asr.json、existing-job-stages.json、failure-evidence.json、qa-runtime.md、qa-audio-metadata.json。真实Edge材料页只读看到本次失败和stage_failed；截图请求超时，不能称截图成功。媒体/账户/日志均不入公开Git。
