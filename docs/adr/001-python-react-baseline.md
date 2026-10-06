# ADR-001 独立 Python + React 基线
日期 2026-10-05；状态：按用户明确方向制定的实施基线，具体依赖由 LIVE-002 验证。
背景：app 是 CPB 副本，Git 未提交，React Demo 已在 frontend/prototype；旧文档混用 Java/Vue 与归档模板。
决定：保留 Demo 迁 frontend/web；新 services/backend；Python3.11/FastAPI/SQLAlchemy2/Pydantic2/Alembic/PostgreSQL；Celery/RabbitMQ、PG 状态真源。
取代旧 Python>=3.14/SQLModel 模板起点与“保留 Java/Vue”规则；CPB 模块逐个迁移，自有账号/部署。
一任务/分支/worktree，独立 Review，串行合并；M0 建基线后才并行。
V1=M0～M4，平台采集=M5；评分待定不阻塞证据复盘。
历史 FDE 任务不派发，改 LIVE 序列；本轮未执行归档/首次提交/远程/后端安装或部署。
