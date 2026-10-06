# LIVE-006B 模型配置改造与迁移指南

本轮把模型选择集中到分层配置和 Model Registry，实际接通既有 ASR 任务。前端仍为 Demo；未调用真实供应商、未下载模型，也未实现总结报告、Agent 或 RAG 业务。详细结构见 [注册表](model-registry.md)，任务命令见 [操作员入口](media-jobs.md)。

## 代码审计与归属

| 文件 | 职责与本轮变化 |
|---|---|
| core/model_config/ | 新增安全文件读取、分层合并、字段类型与来源；私有凭据不序列化 |
| core/model_registry.py | 具名模型与能力校验、不可变描述、完整 v2 快照 |
| workers/media_configuration.py | 新旧配置桥接、可信环境选择、恢复时漂移检查 |
| integrations/asr/factory.py | 统一 ASR adapter 构造；业务不再散落供应商选择 |
| workers/media_jobs.py、media_operator.py | 接入注册表，保留旧任务与单文件入口 |
| config/、.env.example | 共享基础、环境与本机覆盖示例；私有文件不入 Git |
| core/provider_config.py | 保留 v1 加载、快照和协议约束，不重写历史任务 |
| core/config.py | 原有数据库、消息队列、存储 Settings，仍与模型配置分离 |

审计没有发现业务代码硬编码具体供应商或模型名。迁移的是配置加载与 adapter 创建入口。16 kHz、单声道、16-bit PCM 是当前媒体格式契约，25 MB 是转写传输保护上限；这些约束仍保留。分段时长、最大媒体时长、模型名、端点、请求数等才由公开配置控制。没有为了“可配置”而把所有常量变成任意参数。

## 配置顺序与环境

优先级从低到高：内置默认 → config/models.yaml → config/environments/<环境>.yaml → 开发本机 local.yaml → 白名单环境变量。dotenv 中的值低于进程系统环境；只做内存解析，不执行 Shell、不插值、不改变 os.environ，也不向数据库/MQ Settings 注入值。

字典递归合并；列表整体替换；null 是明确值，不是删除指令，不合类型即报错。每一层在合并前拒绝秘密字段以及 URL userinfo/query/fragment，避免上层覆盖隐藏底层凭据。配置来源追踪只记录字段路径和来源，不记录秘密值。当前公开模型集合和别名使用具名映射，类型不允许任意列表替代。

| 运行环境 LIVE_ENVIRONMENT | 可选模型环境 --config-env | 本机覆盖与 dotenv |
|---|---|---|
| development | development/dev、test | 默认读取 config/local.yaml 和 config 父目录 .env（若存在） |
| production | production/prod、staging | 拒绝 local；不自动读取 .env，仅接受显式 --dotenv 私有路径 |

LIVE_ENVIRONMENT 是受信任的部署设置，只支持 development/production。预发布用 LIVE_ENVIRONMENT=production 配合 --config-env staging；不要将 LIVE_ENVIRONMENT 写成 staging。YAML 不能选择部署环境，也不能把生产降为开发。仓库已提供 development、test、staging、production 四个明确命名的环境文件；空映射模板继承基础配置，默认模型全部关闭。未提供环境覆盖文件时也沿用基础配置；*.example.yaml 示例不会自动加载。

白名单环境覆盖仅有 LIVE_MODEL_ASR_DEFAULT、LIVE_MODEL_LLM_DEFAULT、LIVE_MODEL_SEGMENT_SECONDS、LIVE_MODEL_MAX_DURATION_SECONDS。端点和其他参数仍写 YAML；key_env 是密钥变量名，不是密钥值。模型加载器最终只保留被 key_env 引用的私密值，不留存整个系统环境。

## 本地开始配置

在 app 目录执行以下复制，-n 避免覆盖已有文件：

```sh
cp -n config/local.example.yaml config/local.yaml
cp -n .env.example .env
chmod 600 .env
```

团队确认的通用 provider、model、endpoint 与能力参数统一放 config/models.yaml；不同环境的公开差异放 config/environments/<环境>.yaml。本机 local.yaml 只覆盖机器差异，例如 Ollama IP、device 和 model_path，不再复制维护第二套完整配置。个人试配时可以先修改 local.example.yaml 复制出的完整 profile，确认适合共享后将公开字段提升到 models.yaml。真实密钥只在自己的 .env 填写，例如 YOUR_ASR_API_KEY 对应 key_env 的同名引用。保持 enabled: false，直到服务、样本和预算已确认。本轮不会为你读取或填写真实密钥。

新入口必须显式传 --config-dir 的绝对路径；不会自动发现任意 YAML：

```sh
uv run --project services/backend python -m live_review.workers.media_operator submit \
  --workspace-id UUID --admin-id UUID --material-id UUID \
  --config-dir /Users/docfat/Desktop/个人/project/直播体系FDE/app/config \
  --model-id asr.default --config-env development
```

默认配置是关闭的，直接提交会明确拒绝，而非自动选一个供应商。此命令没有网络授权；真实 ASR 需要单任务 --allow-network，与配置启用分别检查。不要将授权写到 YAML 或 .env。v2 无需 source .env；仅支持 KEY=value、整行注释与配对引号，不支持变量、命令替换或 shell 脚本。

生产配置由部署方放置共享基础和 production/staging 覆盖，进程环境传密钥，或显式 --dotenv /绝对路径/私有.env。dotenv 必须是无符号链接的受限普通文件、权限600；启动 worker 也须使用相同的受信任环境和配置路径。项目私有 local 与 .env 已被 Git 忽略，强制暂存私有 local 文件也会被仓库门禁拒绝。

## 新模型与新 Agent

在 models 下添加唯一名称、capability、route 和强类型 parameters，再令 aliases 的能力前缀匹配模型。参看 config/profiles.example.yaml：ASR、LLM、vision、embedding、reranker、detection 均有明确类型边界；temperature、device、model_path、confidence 只允许适合的能力和值；route.timeout_seconds 是严格整数1–600，默认60，并纳入完整快照。

Ollama 可声明本机或局域网地址，如 http://192.168.1.100:11434；HuggingFace 可声明本地模型路径/device；YOLO 可声明检测置信度。当前这些是可校验描述，resolve 明确拒绝执行，不导入对应库、不连接地址、不下载权重。只有既有 ASR 协议具备实际 adapter，ASR 不接受 adapter 尚未消费的额外 parameters。

新增 Agent 先通过真实存在的 API 校验依赖，不直接填写模型名、端点或密钥：

```python
registry.validate_references(["asr.default"], expected_capability="asr")
descriptor = registry.get("asr.default")
captured = registry.snapshot()
```

未来执行新能力仍须实现对应 adapter、授权/资源限制和测试，不能仅新增一条 YAML 就声称已有 Agent、视觉或 RAG 系统。本轮不创建空壳模块。

## 历史任务与重试

旧 --config /absolute/providers.yaml 仍使用 v1 单文件与原有系统环境，不自动加载 dotenv，不能混用 v2 选项。原始已持久任务没有 model_id、locator 或 runtime_environment 也按 v1 恢复，输入不被静默升级。

v2 固定完整有效公开配置、所有模型、参数、别名、可信配置环境及 SHA256；恢复时重新加载并比对完整指纹和配置定位信息。未选模型发生变化也拒绝继续，须恢复旧配置或显式新任务，不能悄悄切换路由。指纹不是签名，密钥轮换也不等于账单账户身份已经核验。

已知响应复用持久缓存，未知结果不自动重放；每任务的网络授权与请求预算仍独立。请求数和媒体时长是硬限制，金额字段只是预算声明，并无实时供应商计费核算。

## 验收证据

本轮独立 PostgreSQL 使用15470 / live-fde-006b，产物在 runtime/live-006b。每次主集成运行创建独立 live006b_suite_<UUID> 数据库，不迁移或清空旧006库。入口：

```sh
uv run --offline --frozen --project app/services/backend python app/scripts/checks/live006b_acceptance.py
uv run --offline --frozen --project app/services/backend python app/scripts/checks/live006b_acceptance.py --suite
```

命令从工作区根执行。默认验证真实 FFmpeg 与 v1/v2 CLI，fixture 文本明确标注 synthetic；suite 显式排除需要独立 broker 的 test_jobs_broker.py，并要求其他测试零跳过。没有在本轮重新声称 RabbitMQ 端到端验收、真实中文识别质量或厂商可用性。最终结果和批准版本以 project-team/reports/LIVE-006B/final-review.md 为准。
