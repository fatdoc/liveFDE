# LIVE-032 视频号协议兼容修复

手机DLNA投屏收到HTTP URI后，旧relay在DNS前以https_required终止。新默认关闭的wechat_https_upgrade仅在视频号record路径传入relay，为允许的wxlivecdn.com默认HTTP端口构造同主机HTTPS候选；涵盖初始URI、HLS各支持资源、每跳重定向，保留签名查询字节及空问号。不更改抖音、不关闭https_only、不回退HTTP、不增加任意域/凭据。

## 实现与验证

- 基线 a84179b；代码作者提交 c45e7a8d6a28921f5671c401b4553b89dd4f7501。同分支后续ARC文档/门禁提交不改变这组实现。独立审查绑定最终提交，见runtime/live-032/qa-fixed-review.md。
- 代码作者最新针对性用例（wechat_https/resolution）59 passed；此前受影响六文件组166 passed/4 skipped，两组重叠，不累计。Ruff通过。后续独立测试与CI结果以runtime/live-032/closure.json为准。
- 原始HTTP语义、空查询、重复参数/编码、伪域/端口/用户信息/控制字符、HLS主从/分片/key/map与重定向、私网DNS拒绝、TLS失败无回退纳入回归。TLS握手失败及时关闭socket。
- 没有API/迁移/依赖/UI改动；候选开关进入现有policy指纹，API/executor必须按同版本和策略重启，仅在无活跃任务/待执行capture outbox时操作。

## 真实证据与限制

原失败任务27f1c170-946a-4778-b31b-ff26ad4aa497已失败；签名URI按内存设计释放，未产录制媒体，无法事后重放。官方最新main与固定源码一致，详见upstream-audit.md。公开README示例主机pull-l1.wxlivecdn.com的证书/SNI/TLS1.3握手成功，但不是用户实际签名URI且未请求媒体，不代表实际CDN播放、手机投屏或录制验收。

本轮不自动创建采集、不调用ASR/LLM。部署后用户重新投屏，只有实际进度、关闭并导入可播放音视频才构成真实验收；失败原样保留，不自动重试。HTTP-only或其他CDN能力仍未知；本修复不保证所有视频号直播可录。

## 部署与回滚

运行证据、原配置备份、进程记录在工作区runtime/live-032；本文为交付候选记录，部署及CI最终状态查closure.json，不能把提交等同上线。目标8199 API/5199页面，保留现有UI/ASR服务、工作区平台/模型配置及媒体，仅运行policy设置wechat_https_upgrade=true。回滚需无活跃任务，停止本轮API/executor，恢复备份策略，再按上轮LIVE-029代码重启同服务；不可在录制中切换，也不删除历史失败/媒体。
