# LIVE-004A 身份与共享 API 基础
- 状态：verified；owner /root/be_live004a；独立review /root/qa_live002，最终由ARC集成。
- 依赖：LIVE-002/003；base da128af；branch feat/LIVE-004A-auth。
- 工作副本：工作区 `.worktrees/live-004a-be`。
- 允许路径：services/backend/src/live_review/core/**、modules/identity/**、modules/__init__.py、main.py、pyproject.toml、uv.lock、migrations/env.py、migrations/versions/0001_identity.py、tests/test_identity.py及必要conftest；本卡与project-team/reports/LIVE-004A/**。其余先协调。
- runtime：runtime/live-004/4a.env（不入库），独立PG15440 live004_4a，材料根storage-4a；不得触碰其他DB或运行预览。
- 范围：管理员CLI/哈希口令/会话、登录轮换/退出/过期/禁用、可信Origin/CSRF、持久并发限流、安全错误、共享身份依赖、实际响应OpenAPI。
- 验收：真实PG新库及重复迁移；CLI与登录/退出/会话失效；Origin/Host/非ASCII CSRF；安全500 request_id；两个workspace身份与注入拒绝；并发限流；生产Secure；Ruff。初审10通过，P2两项修复后提交复审。
- 限制：无RBAC、公开注册、密码重置、前端接入、后台分析、远程CI或部署；pypdf/材料Settings仅支持C集成，实际材料行为归C。
- done需独立最终head批准、ARC集成SHA和本轮PM验收；作者不得自批。

- 本轮集成：A f34319f、B e1c4cb8、C2541817及修复213870d；真实全套32通过/0skip，综合HTTP与增量迁移通过。独立review见对应reports，待PM最终核对。
