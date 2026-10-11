# LIVE-033 AI 服务设置

PM授权参考既有3000项目配置方式，完成设置、独立审查、CI/PR集成及5199/8199部署。base bef361bc95b7eaaac36e6d29568d6c308a1bcab6；feat/LIVE-033-model-settings；工作副本 .worktrees/LIVE-033-model-settings。ARC统筹与前端/共享文件，BE视觉声明、ENG腾讯ASR、QA非作者审查。所有运行证据放runtime/live-033。

默认OpenAI-compatible文本接口/模型/密钥继续使用原配置；视觉可引用默认接口密钥并单独选择模型，或使用独立兼容服务。视觉仅配置声明，analysis_enabled=false且未验证，不执行图片分析；LIVE007/008另排期。腾讯凭据工作区隔离，保存后API和worker实际解析，支持本地/腾讯及现有授权回退。新工作区不继承服务器腾讯凭据，避免跨租户共享；不自动迁移/复制全局密钥。保留文件5MB/约156秒限制。

沿用CAS、Origin/CSRF、只写密钥与0600文件；空白保留既有工作区密钥，清除留下修订状态，不回退全局配置。任务锁定workspace+配置版本，纯本地无云任务不受腾讯配置变动影响。旧文本unknown与request tombstone不得清除或重放。不得调用真实模型、上传真实媒体、开始录制/转写。

路径范围由repository.py登记，无迁移/新增依赖。验收分为后端行为/隔离PG集成、前端真实设置交互、固定SHA独立审查、CI合并、空闲部署与PM页面验收；配置可保存不等于真实模型/业务分析验收。保全所有线上私密配置与原媒体/任务记录。
