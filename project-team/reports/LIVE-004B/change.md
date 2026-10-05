# LIVE-004B 本地变更单
作者ARC-01；依赖base1f4595e；review待独立QA绑定head，无远程PR。

新增PG持久主播/场次模块，以workspace复合FK防跨工作区关联。日期精度保持真实：date只存日期，分钟/秒必须带时区、匹配上海日期与精度。时长null、处理pending，不提供假分析。修订行锁检查expected_revision，同版本并发仅一次成功。

GET sessions支持q（按字面匹配%、_）、streamer_id/platform/status/from/to/limit/offset；日期from含/to不含。明确pagination上限100。修改title/streamer/date/time，更新后revision+1。主API权限复用004A。

实际命令：uv locked sync；Ruff全部backend通过；以runtime/live-004/4b.env的LIVE_TEST_DATABASE_URL运行tests/test_sessions.py，3个集成场景通过（每个包含多个API/PG失败断言），含真实并发、错误日期、CSRF、越权、复合FK、应用lifespan重建后读取。已有Starlette弃用警告保留。没有SQLite/create_all或模型请求。

0002 migration在独立真实PG首次从0001升级；集成阶段还需A→B→C旧数据保留及独立QA。测试源依据SQLAlchemy2更新/锁与PostgreSQL16约束官方文档；不把示例作为真实能力。
