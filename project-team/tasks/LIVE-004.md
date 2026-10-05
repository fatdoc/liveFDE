# LIVE-004 身份、场次与材料
- 状态：verified；owner BE-01；reviewer ARC/独立 BE；QA QA-01
- 依赖：LIVE-002/003
- 允许：backend 包 core、modules/{identity,streamers,sessions,materials}、integrations/storage、migrations、对应 tests；均在 services/backend。
- 进 ready 前拆 LIVE-004A 登录、004B 场次、004C 上传，每个单一 owner/独立范围。
- 验收：Admin登录退出/无公开注册、会话安全；场次持久化；流式上传/finalize、真实类型/大小、SHA256、鉴权Range 206/416、工作区越权失败、重启可读。
- 迁移：唯一 head，PG 新库升级和已有数据升级验证。
- 不做：调用 CPB API、AI分析、未授权公网文件。
- 本轮base da128af；子任务004A身份（be_live004a）、004B场次（ARC亲自实现，必须qa独立审查）、004C材料（eng_live002转岗BE-02）、004-ENG工程环境（eng_live004）。均是实际子代理/当前任务，不是新建侧栏窗口。
- 顺序：A共享身份与0001迁移→B场次与0002→C材料与0003；独立模块可提前编写，依赖提交/审核后串行集成，唯一迁移head。
- 隔离：Docker project live-fde-004/15440；4a/4b/4c/qa/integration五个数据库、角色及storage目录，runtime/live-004，禁止共库迁移和碰旧端口。
- PM验收输入：Admin-only（不实现未确认RBAC）；真实PG/API，空库及A→B→C保留数据升级、鉴权/CSRF/Origin、并发revision、未知时间null、上传未finalize不可用、hash/格式/路径/幂等/Range/跨workspace隔离、进程重启后真实字节可读；实际OpenAPI导出，草案/已实现分开。
- 前端接线仍属012/013；本轮不改Demo，不调用模型或采集平台。
- 交付：功能代码/测试/独立Review完成；统筹接线收尾待独立核对和PM验收。

- 本轮集成：A f34319f、B e1c4cb8、C2541817及修复213870d；真实全套32通过/0skip，综合HTTP与增量迁移通过。独立review见对应reports，待PM最终核对。
