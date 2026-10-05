# 依赖来源与锁定
核对日期 2026-10-05。使用本机 uv 0.9.26 / Python 3.11.15，`uv.lock` 固定完整依赖版本及 hash；pyproject 固定直接依赖。不是最新版本保证，变更必须重锁并验证。

官方依据：
- https://fastapi.tiangolo.com/deployment/versions/ 建议固定经过测试的版本，Starlette 交由 FastAPI 兼容范围解析。
- https://docs.sqlalchemy.org/en/20/intro.html SQLAlchemy 2 系列，Python 3.11 在支持范围。
- https://docs.celeryq.dev/en/stable/getting-started/introduction.html Celery 5.6 系列及 RabbitMQ 支持。
- https://docs.astral.sh/uv/concepts/projects/sync/ 使用 locked 同步，锁与项目变化不一致应失败。
- https://www.psycopg.org/psycopg3/docs/basic/install.html psycopg3 binary 安装方式。
- https://docs.pydantic.dev/latest/concepts/pydantic_settings/ Pydantic2 配置独立 settings 包。

实际安装元数据 Requires-Python：fastapi 0.142.2 >=3.10；pydantic 2.13.5 >=3.9；pydantic-settings 2.15.0 >=3.10；SQLAlchemy 2.0.54 >=3.7；psycopg 3.3.6 >=3.10；Alembic 1.20.0 >=3.10；Celery 5.6.3 >=3.9；uvicorn 0.54.0 >=3.10。uv 解析+本地运行是本组合兼容证据；官方网页不一定描述完全相同 patch。

官方 Docker images 使用 postgres:16.11-bookworm / rabbitmq:4.1.5-management 精确版本标签。首次拉取后记录 digest，生产发布另做镜像扫描/更新评估，本轮不发布。
