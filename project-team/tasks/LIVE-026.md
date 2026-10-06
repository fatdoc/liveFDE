# LIVE-026 抖音CDN HTTPS候选适配

用户明确授权移植原DLR协议适配并实际验证录制。基线8a76d7b；ARC作者，fix/LIVE-026-https-adapter，.worktrees/LIVE-026-https-adapter；QA独立固定SHA审查。仅bridge/test_bridge由ARC修改，目录门禁/文档同owner。无依赖、迁移、UI或全局策略放宽。

依据固定上游add187f8 main.py1150–1151与1820：可将HTTP源转换为HTTPS尝试。只对同时命中当前策略与douyincdn.com边界的HTTP默认端口(隐式或80)生成HTTPS候选；完整保留path/query，不改变签名、不携带Cookie到CDN、不转换任意域/端口/用户信息。已有合格HTTPS优先，其后按FLV/HLS偏好构造候选；仍由受控relay验证TLS/域/IP/逐跳/时限，不回退HTTP。settings check仅静态验证，不伪称媒体连接成功。

审查后一次当前用户授权房间最多60秒/50MB实际采集，先确认旧任务退出；不执行历史被拦探针及变体，不操作本机Docker，不开启其他平台/模型。证据区分单元测试、真实连接、媒体音视频/时长、材料导入和失败；不隐藏未知。原私密workspaceCookie继续使用，不回显不入Git。运行产物runtime/live-026。
