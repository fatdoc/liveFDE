# 架构与数据
本轮实施基线；具体依赖版本在 LIVE-002 安装验证并锁定，不表示已部署。

| 层 | 选择与边界 |
|---|---|
| 前端 | 现有 React + TypeScript + Vite + React Router，npm/package-lock；不回到 Vue 或模板路由 |
| API | Python 3.11 + FastAPI + Pydantic 2；兼顾 CPB 媒体运行时 |
| ORM/迁移 | SQLAlchemy 2 + psycopg 3 + Alembic；ORM/API schema 分开，替代旧 SQLModel 起点 |
| 数据 | PostgreSQL 16 为初始验证目标，选受支持补丁并固定镜像 |
| 耗时任务 | Celery + RabbitMQ；PG 为任务状态真源 |
| 文件 | StorageProvider，开发本地卷、交付可换 S3 兼容存储，大文件不进 DB |
| 媒体 | FFmpeg/FFprobe，Python 参数数组调用 |
| 模型 | DashScope ASR、Qwen VL、DeepSeek 兼容 API，自有配置、隔离 provider |
| 导出 | JSON/人工修订为源，ReportLab 生成 PDF |
| 工具部署 | uv、Ruff、pytest、Docker Compose；不先引入 Redis/Kubernetes |

API 与 worker 同一 Python 包、不同进程，不拆业务微服务。先用同步 SQLAlchemy，同步 DB 放同步路由/任务，不在 async 路由阻塞。
每请求/任务独立 Session，不能跨线程共享。模型本地运行时可隔离，不把大模型权重塞进 API 镜像。
前端轮询任务状态，实测必要后再加 SSE。

## 任务运行
API 同事务写 job + outbox → dispatcher 派发 ID → RabbitMQ → worker 条件领取/租约/心跳 → 保存阶段产物。
消息可能重复，幂等键+唯一约束防重；不是“队列保证恰好一次”。阶段成功以产物持久化为准，报告失败不能显示全任务成功。
取消采用请求/实际停止两阶段；不承诺供应商已中止收费。未知结果的付费调用先核对，不盲重放。

## 数据所有权
| 模块 | 对象 |
|---|---|
| identity | Admin、登录会话、默认 workspace |
| streamers / sessions | 主播、场次、平台、时间 |
| materials | 文件、SHA256、关联、逐字稿版本/片段、截图 |
| jobs | job、stage、attempt、outbox、lease、heartbeat、错误 |
| analysis | analysis_run、证据、候选结构、模型/prompt/规则版本 |
| reports | 单场/周报告、revision、来源版本集合、导出 |
| assets | 资产/修订/审核事件/标签/收藏 |
| preparation | 备播条目、固定资产版本、适配稿、学习/使用记录 |

UUID、workspace_id、created_at/updated_at（UTC）、必要的 revision。媒体定位整数毫秒，未知 null。
周报默认 Asia/Shanghai，周一 00:00 至下周一 00:00 左闭右开，保存 UTC 查询边界、主播与全部来源版本。
文件二进制去重与业务关联分开。重新分析只新增版本，不覆盖人工作品。备播引用 asset_revision_id，撤回后保留历史并提示。

## 认证与审核
Admin 登录，服务端会话+HttpOnly cookie，生产 Secure，同源部署；修改请求校验 CSRF/Origin。密码使用维护中的 Argon2 实现，初始管理员用受控 CLI 创建，无默认密码。
文件、Range、任务、导出均鉴权+工作区校验。模型只能产候选。
业务审核 draft→pending_review→approved/rejected；approved→withdrawn；编辑已审内容产生新待审 revision。
单管理员可业务自审但留审计；这与开发代码禁止作者最终自审不同。
规则未配置 score=null、reason=rules_not_configured，不导入竞赛惩罚。配置快照无明文密钥。

参考：[SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)、[Celery 幂等](https://docs.celeryq.dev/en/v5.5.0/userguide/tasks.html)；引用解释机制，不代表采用页面旧版本号。
