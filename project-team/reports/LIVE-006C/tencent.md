# LIVE-006C Tencent 作者交接

Owner：ENG 子任务 `/root/eng_live002`。工作树 `.worktrees/live-006c-tencent`，分支 `feat/LIVE-006C-tencent`。共享契约依赖 root d47edbf，本树 cherry-pick 为5c3252f；作者提交仅含 Tencent 子树、专项测试、本说明及 docs/asr-tencent.md。本报告不是独立批准或集成验收。

实现文件识别 CreateRecTask/DescribeTaskStatus 与 realtime V2，并发收发、1:1 PCM 节流、原始观察映射、隐私/联网前置检查、脱敏错误、未知付费结果不重试。无DB/迁移/端口/模型下载/真实云调用；依赖锁由 root 管理。详细输入格式、字段、SDK固定版本依据、5MB限制、取消期间socket连接边界见 docs/asr-tencent.md。

验证：专项 pytest 18例（合成数据/mock），Ruff check/format；覆盖签名绑定、file成功/失败/未知、隐私拒绝、缺时间戳、文件尺寸、V2两种sentence形状、节流、说话人-1、断连无重连、输入停滞、发送异常、运行中取消及建连取消清理。未验证真实腾讯请求、识别质量、计费或正式部署。作者测试不能代替 QA 绑定提交 SHA 的独立Review。需要 root 集成公共契约最新字段与 websocket-client 锁后再运行受影响测试。

回滚：独立撤销作者提交；无迁移或数据修改。后续长文件需要明确的上层分片/存储设计，当前不隐式上传或绕过5MB上限。网关负责持久预算/调用意图，不得因 provider unknown 自动重试。
