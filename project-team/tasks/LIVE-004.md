# LIVE-004 身份、场次与材料
- 状态：backlog；owner BE-01；reviewer ARC/独立 BE；QA QA-01
- 依赖：LIVE-002/003
- 允许：backend 包 core、modules/{identity,streamers,sessions,materials}、integrations/storage、migrations、对应 tests；均在 services/backend。
- 进 ready 前拆 LIVE-004A 登录、004B 场次、004C 上传，每个单一 owner/独立范围。
- 验收：Admin登录退出/无公开注册、会话安全；场次持久化；流式上传/finalize、真实类型/大小、SHA256、鉴权Range 206/416、工作区越权失败、重启可读。
- 迁移：唯一 head，PG 新库升级和已有数据升级验证。
- 不做：调用 CPB API、AI分析、未授权公网文件。
- 交付：未执行；资源/分支/SHA/命令/Review待实际填写。
