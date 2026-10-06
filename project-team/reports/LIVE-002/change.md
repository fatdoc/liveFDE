# LIVE-002 本地变更单
- base：ca9de2b；branch feat/LIVE-002-foundation；作者 ENG 子任务 /root/eng_live002；无远程 PR。
- 问题/结果：从前端Demo基线增加独立Python工程、依赖环境、迁移入口、健康检查和可重放门禁。没有业务API或AI分析。
- 路径：见任务卡；未改前端源码/锁、STATUS、003契约或原CPB。
- 框架：FastAPI/Pydantic2/SQLAlchemy2/psycopg3/Alembic/Celery；直接依赖及uv全量锁定，版本与官方来源见dependencies.md。
- 变更：dispatcher仅--check预检；worker无业务任务/result backend；Alembic无业务修订；ready只检查PG+MQ，不代表worker可用。
- 环境：工作区runtime/live-002，Docker postgres独立bind；原生RabbitMQ独立节点/数据；不连接5432/6379，不修改Demo5188。
- 初审修复：限制smoke DSN与环境覆盖/目录真实边界；CI按task/base检查owner；实测跨owner rename失败；依赖故障需匹配单独down字段。
- Review：独立qa_live002批准18e721f3c123b064104c90d94732374d6ed80063，记录review.md；main串行集成19fede3。
- 回滚：revert本任务提交；只停止本任务容器/进程，保留数据，不删用户卷。
