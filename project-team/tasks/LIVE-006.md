# LIVE-006 媒体与 ASR 适配
- 状态：in_progress；owner AI-01；reviewer ARC + BE 契约审查；QA QA-01
- 依赖：LIVE-002/003；可与 LIVE-004 并行
- 允许：services/backend/src/live_review/integrations/{media,asr}、对应 tests、docs/ai；依赖变化交 ENG。
- 目标：FFprobe/FFmpeg→16kHz单声道WAV→ASR→全局毫秒时间轴，保留来源/模型与完整性。
- 验收：合成样本格式/时长、分段合并偏移、无音轨/损坏文件/超时/分段失败；provider契约测试；真实样本与账号就绪后另做付费smoke并记录用量。
- 不允许：复制 CPB 密钥、强制所有环境安装说话人模型、写资产表、缺词仍标完整成功。
- 交付：MEDIA/ASR作者实现与23项自检已完成，见reports/LIVE-006/change.md；配置与005队列接线独立进行，待最终SHA独立Review/QA与集成。

- MEDIA/ASR作者 /root/eng_live002；worktree .worktrees/live-006-media；branch feat/LIVE-006-media；base43dc947。仅media/asr、两测试文件、docs/ai/media-asr.md、本卡与change.md。
- 实际产物 runtime/live-006/media-author；不调用付费模型；兼容协议使用MockTransport。

## 统筹接线与集成验收

- 用户经PM另行授权YAML配置与视频抽音/带时间戳转写，真实调用前确认配置/预算；不进入007/008。
- CFG519e313、MEDIA1ce1b46、JOBS802dfe8均由/root/qa_live002独立批准；原作者未自批。
- 增补精确写范围见scripts/checks/repository.py的LIVE-006-CFG/JOBS/ARC及资源表；依赖锁CFG独占。
- 实际上传→材料→operator→005受控进程→manifest/转写引用成功；126后端测试通过/0skip（明确排除broker-only文件），28工程检查通过。最终组合Review与PM收口待完成，见reports/LIVE-006/integration.md。
