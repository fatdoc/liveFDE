# LIVE-004A 本地变更单

Base: da128af。Owner: /root/be_live004a，分支 feat/LIVE-004A-auth。

实现管理员 CLI 引导、Argon2id 口令、数据库哈希会话、登录轮换、退出、过期与停用检查；Origin 配置白名单与 Fetch-Metadata、CSRF；可信地址取直连 peer，不信任代理转发头；PG 行锁限流跨进程持久化。统一错误/请求 ID/private,no-store。首版单客户管理员角色；workspace 从身份派生，不接受登录请求 workspace 注入。

共享入口 core.database.get_db（关闭而不隐式提交）、core.auth.current_admin/require_mutation、core.errors.ApiError。identity.models.Workspace/Admin 供外键引用。0001_identity 为首个迁移，无 create_all。

CLI: 在 services/backend 下使用 `uv run python -m live_review.modules.identity.cli --username <name> --display-name <name> --workspace-name <name>`；密码交互 getpass（12–1024字符），自动化可 --password-stdin，禁止把密码放参数。生产设置 LIVE_ENVIRONMENT=production 与精确 HTTPS LIVE_TRUSTED_ORIGINS JSON 数组，Cookie Secure；开发明确非 Secure。

自检：在 runtime/live-004/4a.env 指向的独立 PG 15440 执行真实迁移（首次空库和重复 upgrade），pytest 13 passed（10 identity + 3 existing health），Ruff pass。覆盖登录/旧cookie轮换失效/退出/过期/禁用/恶意Origin与Host/CSRF/安全错误/拒绝workspace注入/并发限流/真实CLI哈希、两个独立workspace身份、token仅哈希落库和生产Secure配置。测试通过 LIVE_TEST_DATABASE_URL 显式启用；无该变量时集成用例 skip，不宣称通过。

依赖来源：argon2-cffi==25.1.0 官方 https://argon2-cffi.readthedocs.io/en/stable/howto.html ，pypdf==6.19.0 官方 PyPI https://pypi.org/project/pypdf/ （材料模块请求，使用由 LIVE-004C 实现）。uv.lock 固定完整解析结果。

限制：独立初审发现非ASCII CSRF错误500、兜底500缺响应请求ID两项P2，均已修复并新增真实请求回归，最终996b4f4已独立复审批准；前端接入、RBAC、多客户 SaaS、密码重置、会话/限流历史清理不在本任务。代理部署需另审 origin 与客户端地址方案（当前不信任任何 forwarding header，代理下按代理 IP 共享限流）。无远程 CI、无上线。

回滚：停 API，先撤销后续依赖迁移再降级 0001（会删除身份数据，仅空开发库适用）；已有真实客户身份库只前向修复。凭证位于 runtime，不入 Git。

复审修复：CSRF非ASCII直接403且保留会话；统一错误生成同时写body/header请求ID，真实未捕获异常500回归验证；login/me增加LoginResponse/UserView response_model，实际OpenAPI有可生成类型的schema，logout204无body。补任务卡，真实PG13项通过、Ruff通过。
