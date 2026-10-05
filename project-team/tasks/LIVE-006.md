# LIVE-006 媒体与 ASR 适配
- 状态：backlog；owner AI-01；reviewer ARC + BE 契约审查；QA QA-01
- 依赖：LIVE-002/003；可与 LIVE-004 并行
- 允许：services/backend/src/live_review/integrations/{media,asr}、对应 tests、docs/ai；依赖变化交 ENG。
- 目标：FFprobe/FFmpeg→16kHz单声道WAV→ASR→全局毫秒时间轴，保留来源/模型与完整性。
- 验收：合成样本格式/时长、分段合并偏移、无音轨/损坏文件/超时/分段失败；provider契约测试；真实样本与账号就绪后另做付费smoke并记录用量。
- 不允许：复制 CPB 密钥、强制所有环境安装说话人模型、写资产表、缺词仍标完整成功。
- 交付：未执行；版本来源/配置/实际验证/SHA/Review待填。
