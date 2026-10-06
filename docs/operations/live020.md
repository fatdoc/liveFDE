# LIVE-020 原生联调环境

本轮是本机开发验收，不是客户部署。工作区 `runtime/live-020` 独立保存 PostgreSQL、媒体、配置及证据，不提交 Git。旧环境保持原样；不使用本机 Docker。

| 资源 | 本轮目标 |
|---|---|
| PostgreSQL | 127.0.0.1:15500，数据库/角色 live020 |
| API | 127.0.0.1:8199 |
| React 开发预览 | 127.0.0.1:5199，代理 API8199 |
| 视频号 DLNA | 配置端口8200；接收器及真机待验 |

`live020_environment.py` 只读取本轮0600私有配置，拒绝其他数据库/端口/存储目标，清除继承的 LIVE_* 变量，仅允许显式抖音cookie透传；开发可信来源固定5199。初始采集策略关闭，初始模型注册表不启用供应商。身份账号保存在runtime私有文件，不写入报告或日志。

在对应工作副本根执行：

```sh
services/backend/.venv/bin/python scripts/checks/live020_environment.py --configure-db
services/backend/.venv/bin/python scripts/checks/live020_environment.py .venv/bin/alembic upgrade head
services/backend/.venv/bin/python scripts/checks/live020_environment.py .venv/bin/uvicorn live_review.main:app --host 127.0.0.1 --port 8199
```

环境脚本不创建/清空数据库。原生集群由统筹一次性创建并确认端口空闲；已有目录不覆盖。开发数据库账号仅用于隔离本地验收，不作为交付账号。

`live020_acceptance.py` 依赖LIVE-020实现及其 `test_capture_executor.py`，应在集成副本或CAP副本运行。每次创建唯一 `live020_suite_<uuid>` 库，证据保留到runtime，不复用应用库。测试可信来源单独固定5188以匹配既有fixtures；缺少JUnit、零用例、失败或跳过均不能通过。`--all` 覆盖后端套件但明确排除需真实MQ的 `test_jobs_broker.py`，不能声称本轮验了MQ。完整MQ回归由既有CI提供。

采集执行器的配置/启动以 `docs/capture.md` 为准。前端模拟、合成媒体真实链路、独立进程停止、真实抖音/视频号分别报告；没有真机或直播来源时不写已通过。此前被自动安全检查中止的探针不重跑，也不换工具规避。
