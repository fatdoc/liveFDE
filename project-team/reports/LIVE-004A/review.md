# LIVE-004A 最终独立复审：批准

Reviewer：/root/qa_live002；日期 2026-10-05。
批准代码 Head：996b4f42a84ad273d5d45c0081b16c6d5cbae56d；base da128af。
结论：**批准该 SHA 进入本地串行集成；初轮两个 P2 均修复。** 验证前后 HEAD 一致、工作树干净，未改代码或提交。批准仅覆盖身份及共享 API 基础，不代表整个平台或生产发布验收。

## 最终独立验证

- ENG 新建专属空库 live004_qa_identity / 专属同名 role，127.0.0.1:15440；凭证只从 runtime/live-004/qa_identity.env 注入测试子进程，先校验 host/port/db/user，不打印密码。
- `uv run --project services/backend pytest services/backend/tests -p no:cacheprovider`，设置 LIVE_TEST_DATABASE_URL 为上述专用库：**13 passed、0 skipped**，15.29 秒，保留 Starlette/httpx 弃用警告。
- 真实迁移从空库升级并重复 upgrade，最终 version=0001_identity；登录/轮换/注销/过期/禁用、双工作区身份、CLI Argon2id、哈希会话、并发持久限流、Origin/CSRF、安全错误、生产 Secure 等原回归全通过。
- 非 ASCII CSRF 0xff 回归返回403 csrf_rejected，X-Request-ID与body一致，会话仍有效；统一500 handler同样具有一致请求ID、安全错误与no-store头。
- Typed LoginResponse/UserView明确公开字段，OpenAPI login/me引用该模型，logout204无响应体。
- Ruff显式项目配置：通过。
- 在A worktree执行当前main绝对路径的 `app/scripts/checks/repository.py --task LIVE-004A --base da128af`：0 violations。A自身旧门禁尚无任务注册，使用的是ARC维护的新版共享门禁；集成时需保留新版。
- 只读确认已有共享QA库 live004_qa 仍为0002_sessions。没有清空或降级B留下的QA迁移证据，没有连接作者4a库，没有操作其他服务。

## 限制与交接

无公开注册、密码重置、RBAC、前端接入、真实模型、远程CI或发布验收。生产代理配置/客户端地址方案按原变更单另审。身份测试清理的是A专用库合成数据；迁移及运行数据库保留。QA资源锁归还ARC，集成后运行受影响检查；后续代码变化需对应复审。

---

以下保留初轮问题与验证轨迹（结论已被上述最终批准取代）。

# LIVE-004A 独立审核

Reviewer：/root/qa_live002；日期 2026-10-05。
Base：da128af；审查 Head：1f4595e519783f601dcb6d85e04bb758a8acb502；工作树干净。
初轮结论：P2 待作者修复，暂不最终批准。

## 独立已验

仅将 runtime/live-004/qa.env 注入子进程，先断言 DSN 为 127.0.0.1:15440/live004_qa。不打印凭证，不连接作者4a库，不drop库。
- 真实 PostgreSQL 全套 tests：10 passed，无 skipped；Argon2、CLI、迁移重复升级、登录轮换、注销、过期/禁用、双工作区身份、Origin/CSRF、持久化并发限流、Secure cookie均通过；保留Starlette httpx弃用警告。
- Ruff：通过。
- `repository.py --base da128af --task LIVE-004A`：当前分支未注册任务而拒绝执行，已向ARC同步；共享门禁需由ARC协调并在集成时复测。
- 手工审阅迁移0001、ORM模型、CLI、设置、会话随机token哈希存储、限流事务与错误处理。未见鉴权绕过或跨工作区身份注入。

## 需要修复

**P2：非法CSRF头导致500。** core/auth.py require_mutation 直接compare_digest两个str，HTTP原始字节0xff在ASGI解码为非ASCII字符串，触发TypeError而非403。独立QA库创建合成账号登录后，POST /api/v1/auth/logout附该头，实测500 internal_error；应安全拒绝并添加回归。

**P2：兜底500缺失请求ID响应头。** 上述请求body有request_id，但X-Request-ID缺失。middleware未从异常返回，而外层Exception handler调用response没有设置该头。建议统一response设置头，使500也可按request_id追踪。

作者已收到问题，等待修复提交后绑定新SHA重测。没有修改代码或提交，也没有操作其他服务。当前没有远程CI/发布或付费模型调用。
