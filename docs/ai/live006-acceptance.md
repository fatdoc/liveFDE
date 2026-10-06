# LIVE-006 验收入口与证据边界

> 本文保留 LIVE-006 的 v1 单文件配置/历史验收说明。LIVE-006B 新增分层 v2 与安全 dotenv 解析，见 [配置迁移指南](configuration-refactor.md)。旧 --config 仍不自动读取 dotenv；新 --config-dir 才使用分层加载，两种入口不可混用。

本轮目标是材料上传后由操作员提交抽音频与转写任务；前端仍是 Demo，没有新增分析任务 HTTP 创建接口、视觉理解或总结报告生成。网络模型默认关闭。

## 四类证据

1. 真实本地媒体：FFprobe/FFmpeg 解码、16 kHz 单声道 PCM WAV、分段文件、来源哈希、音轨偏移与全片毫秒位置。
2. 离线 fixture：预先写好的合成文本，标记 synthetic；证明任务编排、时间换算和产物保存，不证明语音识别正确率。
3. MockTransport：可用 `/audio/transcriptions` 协议适配器的请求与响应测试，证明 multipart/时间戳/预算/失败处理；没有真实网络调用。
4. 真实供应商：本轮未授权、未执行。厂商兼容性、中文识别质量、长音频服务限额、价格和实际费用均待用户指定配置与预算后另验。

YAML 及密钥引用说明见 [配置](provider-configuration.md)，源项目参考见 [核对记录](banana-reference.md)，媒体实现见 [媒体与 ASR](media-asr.md)，任务入口见 [操作员任务](media-jobs.md)。

## 独立运行资源

唯一产品 checkout 是工作区下 `app`。媒体与数据库产物全部在 `../runtime/live-006`；数据库仅本机 `15460/live006` 及本轮生成的 `live006_suite_<UUID>` 独立回归库，Compose project `live-fde-006`。不复用或清空 LIVE-004/005 数据。私有环境文件 mode600，不提交 Git，不在终端打印。

在工作区执行：

```sh
python3 app/scripts/checks/live006_environment.py
uv run --offline --frozen --project app/services/backend python app/scripts/checks/live006_smoke.py
uv run --offline --frozen --project app/services/backend python app/scripts/checks/live006_smoke.py --regression
```

烟测从本轮受保护的环境文件加载目的地址，自行检查固定数据库和存储位置。生成合成视频、真实登录并上传材料、关联场次，然后调用操作员 CLI 提交/执行两阶段任务，结果和日志保留在 `runtime/live-006/integration/<run-id>/`。每次使用新合成账号/场次/材料，保留验收证据，不删除旧记录。回归模式在同一个专用PG15460实例创建唯一live006_suite_<UUID>数据库，核验实际库名/角色且全套子进程继承数据库URL，避免历史outbox干扰测试；每次target.json登记无密钥目标。保留测试数据库，不清空已有表。

烟测经 FastAPI TestClient 调用真实路由及 PostgreSQL，并由独立 Python 子进程运行005任务执行器。**本轮不经过 RabbitMQ，不声称重新完成消息投递端到端验收**；队列投递既有证据见 LIVE-005。下游 FFmpeg 继承受控 handler 进程组。

## 后续真实调用所需确认

用户需确认：服务商与 ASR 模型；支持 verbose_json 分段时间戳的转写端点；YAML profile 和版本；密钥所在环境变量名称；获准处理的音视频样本；最大时长、请求数和金额预算。不要把实际密钥粘贴到任务聊天或 Git。

操作员入口的 `--allow-network` 是单个任务的明确授权开关。没有该开关不建立真实请求；本轮的运行命令不使用它。任务创建时固定无密钥配置快照；重试遇到配置改变会拒绝，需恢复原配置或明确创建新任务。已知分段响应保存后复用，结果未知的请求不自动重放。请求/时长是硬限，美元字段是授权声明，没有厂商价格时不能声称精确美元费用控制。

最终绑定的源码版本、独立 Review、测试计数和实物位置以 `project-team/reports/LIVE-006/final-review.md` 为准；本文提供操作方式而非提前宣布验收完成。
