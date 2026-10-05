# LIVE-006 YAML 配置变更单

Owner /root/be_live004a（CFG/ENG），base43dc947，branch feat/LIVE-006-yaml，worktree live-006-config。作者不自批；独立QA与集成待ARC安排。

新增严格安全YAML加载、ASR/text/vision具名不可变模型、媒体参数、canonical快照与恢复、重试完整指纹校验；默认unconfigured，单独显式离线合成示例且production禁止。实际ASR配置必须声明audio_transcriptions操作，resolve默认不授权真实执行；显式allow_network=True才在内存解析环境key。text/vision仍unsupported，无跨厂商fallback。本轮未读取真实凭证/探测供应商/付费。

新增PyYAML==6.0.3并固定锁，httpx==0.28.1由dev移runtime供媒体传输；接口已与ARC/媒体作者约定，由ARC接线，未改worker/jobs/main。

自检：37项配置测试通过，Ruff通过。覆盖重复键、alias/tag、深度/大小/事件上限、路径/类型/非有限值、明文secret/URL秘密拒绝、不可变快照/篡改/参数变更重试拒绝、production fixture拒绝、真实ASR默认授权拒绝、显式合成env密钥仅内存、inactive完整profile、audio协议校验和无fallback。合成文本与example.invalid仅测试数据；无数据库或供应商调用。

边界：预算字段不是执行账本；未来实际adapter需请求次数/费用持久计数、授权、DNS/出口限制。密钥引用固定不代表供应商账号被绑定，旋转可改变账户；文档明确。只证明配置模块，媒体/集成验收另列。回滚revert代码，已有任务快照不可改写伪装兼容。
