# LIVE-032 视频号受限 HTTPS 候选适配

用户经 PM 明确要求对照原开源项目修复真实手测 https_required，并完成独立 QA/CI/部署，再由用户手动重试；禁止自动重放录制、ASR、LLM。

- 基线 a84179b；分支 fix/LIVE-032-wechat-https；工作副本 .worktrees/LIVE-032-wechat-https。
- 代码 owner ENG 子任务 eng_live032；ARC 负责任务、目录门禁、文档、串行集成部署；独立 QA 绑定最终 SHA。
- 允许代码路径：capture 的 policy/relay/recording/hls/wechat_url 与 test_capture_wechat_https.py、config/capture-policy.example.yaml。ARC 附加 scripts/checks/repository.py、docs/capture.md、本任务与 reports/LIVE-032/。
- 无迁移/API/UI/模型/依赖变化。开关默认关闭，运行时仅视频号启用。抖音及全局 HTTPS 要求保留。

固定上游与本轮查询官方 main 均为 07271abdb5707cf8074483a33c2519b457ccc669。上游 DLNA 从 SOAP CurrentURI 解码返回原地址，CLI 直接 ffmpeg -re -i URI -c copy，无强制 HTTPS、特殊 Cookie/Referer 或事前 TLS 探测。本系统已接收到 URI，但全局 HTTPS-only 在首次 DNS 前拒绝 HTTP；不能把该错误解释为 CDN 不支持 HTTPS。

实现仅对同时命中配置白名单与 wxlivecdn.com 域边界的默认 HTTP 端口构造同 host 的 HTTPS 候选；保留 path/query 原字节和空问号。Relay 统一处理入口、HLS master/variant/segment/key/map 等所有已支持 URI 与逐跳 redirect，不只改 Finder 返回值。每次实际连接继续验证 TLS、域名、公网 DNS 固定与期限。不回退 HTTP、不带凭据到 CDN、不扩大任意域。

原失败任务 27f1c170-946a-4778-b31b-ff26ad4aa497 的签名 URL 未持久化且进程已退出；只能复核脱敏终态。上游示例 pull-l1.wxlivecdn.com 的证书/SNI/TLS1.3握手实测通过，但不是用户临时 URI，也未请求媒体，不作为签名兼容或真实录制验收。真实手机重投、媒体连接、材料导入/音视频验收由用户部署后手测。

运行配置/日志/脱敏证据均在 runtime/live-032；仅在确认无活跃或待处理采集后部署，保留平台凭据/模型/历史媒体。测试与 CI 不替代真实录制。
