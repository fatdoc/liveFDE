# PPT 项目配置参考核对

2026-10-06 只读核对通用版 `/Users/docfat/Desktop/work/Project/github/banana-slides`，HEAD `4e7c922c0e143aabbec4b9e9f835b86306952896`。该工作目录有他人的未提交修改；没有修改源项目、读取其私有配置或复用其账号与服务。

| 实际文件 | 参考内容 | 本项目处理 |
|---|---|---|
| `backend/services/provider_config.py` | `ProviderConfigSnapshot`、`MappingProxyType` 固定任务配置；含密钥因此禁止序列化 | 使用嵌套不可变模型与指纹，持久快照只含公开字段和 key_env 引用；执行时才解析密钥 |
| `backend/services/task_manager.py` | 提交时捕获配置，执行时核验任务与配置 owner | 任务创建时保存配置快照；恢复/重试校验当前配置一致性 |
| `backend/services/ai_providers/__init__.py` | 按能力选择适配器 | 本项目区分 asr/text/vision，仅本轮 ASR 有传输实现 |
| `backend/models/settings.py`、`backend/config.py` | 数据库设置覆盖和环境变量，分别配置 text/image/caption | 遵循本项目要求改为 YAML 显式配置；不照搬数据库优先级、默认厂商或跨供应商密钥兜底 |

PPT 项目的模型配置主体并非 YAML。其 `prompts/*.yaml` 是提示词资源，与模型路由配置不同。本项目使用 YAML 是本次用户要求，不声称原项目已有相同实现。也不复制 Flask 的兼容层或含密钥的内存快照。

ASR 使用明确的 `audio_transcriptions` 兼容协议：multipart file/model、`verbose_json`、`timestamp_granularities[]=segment`，解析秒级 start/end 后转换为全片毫秒。该协议不等于已选择 OpenAI 厂商，也不保证任意聊天兼容模型具有 ASR 能力。

协议依据：[官方转写接口](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create)、[语音转文本指南](https://developers.openai.com/api/docs/guides/speech-to-text)。不同模型支持的返回格式和时间戳能力不同；本轮仅 MockTransport 验证请求和响应，未调用真实服务。
