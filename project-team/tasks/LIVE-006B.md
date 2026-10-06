# LIVE-006B 分层模型配置与注册表

- 状态：in_review；base74df3b1fed59079abcb3f8c8b5cebc47b7e68deb；用户经PM明确授权；PM只读产品验收。
- CFG /root/be_live004a：.worktrees/live-006b-config，feat/LIVE-006B-registry。允许core/model_config/、core/model_registry.py、tests/test_model_config.py/test_model_registry.py、config/共享配置、.env.example、docs/ai/model-registry.md、reports/LIVE-006B/config.md。
- BE /root/eng_live002：.worktrees/live-006b-jobs，feat/LIVE-006B-jobs。允许workers/media_jobs.py/media_operator.py/media_configuration.py、integrations/asr/factory.py及__init__.py、tests/test_media_jobs.py/test_media_registry_jobs.py、docs/ai/media-jobs.md、reports/LIVE-006B/jobs.md。
- ARC /root：主checkout串行集成；.gitignore、scripts/checks/repository.py及对应门禁测试、006B独立验收driver、docs/04-directory-contract.md、docs/ai/configuration-refactor.md与旧配置说明兼容更新、STATUS/access/本卡/本轮报告；需要时更新既有验收driver的边界说明，不改旧历史证据。
- 独立QA /root/qa_live002：指定SHA/候选树只读审查；runtime/live-006b下记录。作者不自批。所有新工作副本/运行物仍在工作区；无remote，不声称PR/部署。

## 目标与规则

默认→共享基础YAML→可信环境覆盖→本机local覆盖→白名单env覆盖；.env低于系统环境，仅内存合并，不污染os.environ，不执行Shell或插值。每层均拒绝秘密值字段，密钥仅*_env引用；来源追踪不泄露值。

ModelRegistry.get('asr.default'/'llm.default')提供具名不可变模型描述；ASR实际业务走registry/adapter，只有ASR执行实现。新Agent通过模型ID引用和能力校验接入，当前不创建Agent/RAG业务或空壳provider。dev/development/test、staging、prod/production映射与生产安全策略明确；生产不可误加载开发local/.env。

旧--config单文件与v1已持久任务显式兼容，不静默迁移；v2保存最终合并后的完整公开配置及指纹，重试漂移拒绝。allow-network仍为每任务独立授权，不接受YAML/env替代；unknown调用不可重放。禁止真实模型调用、现有秘密读取、权重下载；不启动007。

验收：层次/合并/来源/字段与类型/禁用门控/快照/秘密边界/旧任务恢复；真实隔离PG与FFmpeg任务回归，传输仅MockTransport；独立Review后集成，PM最终验收才done。

作者最终CFG a2753fb / JOBS7216234已独立批准并分批集成；主204后端tests零跳过、36工程checks与v1/v2烟测通过，等待最终组合QA与PM范围验收。见reports/LIVE-006B/integration.md。
