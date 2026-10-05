# LIVE-006 媒体与 ASR 适配
- 状态：done；owner AI/CFG/BE/ARC；独立 reviewer /root/qa_live002；PM-01最终验收通过
- 依赖：LIVE-002/003/004/005；已完成材料与任务接线
- 允许：services/backend/src/live_review/integrations/{media,asr}、对应 tests、docs/ai；依赖变化交 ENG。
- 目标：FFprobe/FFmpeg→16kHz单声道WAV→ASR→全局毫秒时间轴，保留来源/模型与完整性。
- 验收：合成样本格式/时长、分段合并偏移、无音轨/损坏文件/超时/分段失败；provider契约测试；真实样本与账号就绪后另做付费smoke并记录用量。
- 不允许：复制 CPB 密钥、强制所有环境安装说话人模型、写资产表、缺词仍标完整成功。
- 历史初稿：MEDIA/ASR作者首次23项自检；独立问题修复后33项媒体测试通过。最终交付配置、媒体、005接线，见reports/LIVE-006/final-review.md。

- MEDIA/ASR作者 /root/eng_live002；worktree .worktrees/live-006-media；branch feat/LIVE-006-media；base43dc947。仅media/asr、两测试文件、docs/ai/media-asr.md、本卡与change.md。
- 实际产物 runtime/live-006/media-author；不调用付费模型；兼容协议使用MockTransport。

## 统筹接线与集成验收

- 用户经PM另行授权YAML配置与视频抽音/带时间戳转写，真实调用前确认配置/预算；不进入007/008。
- CFG519e313、MEDIA1ce1b46、JOBS802dfe8均由/root/qa_live002独立批准；原作者未自批。
- 增补精确写范围见scripts/checks/repository.py的LIVE-006-CFG/JOBS/ARC及资源表；依赖锁CFG独占。
- 实际上传→材料→operator→005受控进程→manifest/转写引用成功；126后端测试通过/0skip（明确排除broker-only文件），28工程检查通过。最终组合Review与PM收口通过，代码649eb0759d1adf397e24f09b9ba458e612989939；批准树a994b27d04d219301d27ac674f909f09b1ee56d2与提交树一致，见reports/LIVE-006/final-review.md。
