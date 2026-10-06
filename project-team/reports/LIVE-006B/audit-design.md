# LIVE-006B 开发前审计与设计

2026-10-06，基线74df3b1，开始时main clean。只审新产品services/backend，不读取旧CPB/PPT或现有私有env。

## 已核实

- core/provider_config.py：单YAML严格加载、asr/text/vision固定槽位、v1不可变快照、显式授权后环境密钥引用；没有层叠配置、dotenv自动加载或具名模型注册表。
- workers/media_jobs.py：submit/load_context各自读YAML；make_provider直接选择offline/兼容ASR。模型名、端点与预算来自YAML，没有硬编码某厂商；需要迁移的是配置读取与adapter创建入口。
- integrations/asr/compatible.py：唯一真实模型传输路径，默认禁网，25MB协议文件上限、回复大小/时间限制；本轮不调用它的真实网络路径。
- media pipeline/CLI的300/600/30为可覆盖默认值；16kHz/单声道/16-bit PCM为既有格式契约；25MB等为协议与资源上限，不将所有常量改为随意覆盖。
- core/config.py为应用基础设施Settings，DB/MQ/存储仍独立配置；LIVE_ENVIRONMENT是可信部署上下文，不由模型YAML定义。core/database.py的连接statement_timeout不是模型配置。
- .gitignore已忽略.env但尚无config/local.yaml规则；目录门禁尚不接受config顶层和根.env.example，需要一起登记。

## 设计与写范围

core/model_config按读取/合并/验证划分职责；core/model_registry提供get/resolve/v2snapshot。config/存共享基础/环境/本地示例；local真实覆盖和.env不跟踪。优先级：内置默认→共享基础→指定可信环境→local（仅开发）→显式白名单env；系统env高于dotenv。每层先验证秘密字段与YAML安全，避免覆盖掩盖秘密；最终合并配置验证字段与类型。默认关闭，不因新增service/model参数变为调用授权。

ModelRegistry返回不可变描述；adapter在执行阶段经授权解析秘密。v2任务持久来源定位和最终公开快照，恢复时重算并严格比对；v1任务保留旧单文件/旧指纹，不重写已持久输入。新Agent/RAG只说明如何引用registry和检查能力，不创建没有业务消费者的运行框架。

每个模块独占写范围与worktree见任务卡；CFG与BE并行，ARC负责门禁/目录/集成/完整报告。独立QA验收秘密边界、生产隔离、逐层合并、旧新任务、实际ASR入口。完整交付报告将列文件、优先级、迁移/保留硬编码及本地/生产/新模型/新Agent操作步骤。
