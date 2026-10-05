# LIVE-005 BE 最终独立 Review

Reviewer /root/qa_live002；日期2026-10-06。
批准Head：3c5ee4ed33fba8bc1bcfa1dcc2227cb9d3ebf66f。
BE差异base：bef80ef（共享配置cd85a6e依赖）；任务起点8cc9ea5。
结论：**批准该BE提交进入本地串行集成**。不等于统筹正式接线/真实多进程故障验收完成；后两者仍须独立审核。作者与审核者不同，未改源码或索引。

## 独立实际验证

经ARC授权取得QA专属PG/vhost及节点不被重启的锁，仅从runtime/live-005/qa.env注入环境；先断言DB为postgresql+psycopg/127.0.0.1:15450/live005_qa且同名user，MQ为amqp/127.0.0.1:5675/live005_qa且同名user，无query/fragment。未打印凭证、未使用BE库。

`uv run --project services/backend pytest services/backend/tests/test_jobs.py services/backend/tests/test_jobs_broker.py services/backend/tests/test_job_config.py -p no:cacheprovider`，显式设置LIVE_TEST_DATABASE_URL：**20 passed、0 skipped，20.40秒**（jobs14、broker1、config5）。仅现有Starlette/httpx弃用警告。

覆盖实际PG最终0004与metadata一致；job/outbox原子回滚；阶段artifact/duplicate；并发HTTP retry幂等、旧attempt/lease拒绝；skipped保留；真实独立spawn handler取消停止；未知intent阻止重试、已知结果复用；跨workspace读取/取消；真实RabbitMQ持久消息确认和载荷、重复执行不改结果。broker测试读取真实消息后调用runner，**不能代替真实Celery消费ACK间隙/kill测试**，后者交ARC脚本补证。

Ruff backend/scripts通过；使用main绝对repository.py --task LIVE-005 --base bef80ef，0 violations。验证前后HEAD一致、worktree干净。

## 预审问题关闭

- P1：无法终止/join handler现抛专用StopUnconfirmed，runner映射execution_stop_unconfirmed，GET can_retry=false且retry409。精确进程边界mock及实际PG映射测试均通过，不再当普通stage_failed自动重试。
- P2：retry同事务追加Job.attempt_history，保留旧attempt安全error、stage状态/reason/产物/completed_attempt；JobOutput显式类型可查。并发相同key重放只保留一次历史，不覆盖成功/跳过阶段。当前attempt保留主表，历史JSONB无分页限制已在change说明。
- 统筹独立child PGID兜底清理修正已另作mock：仅登记日志PID且ps仍为multiprocessing.spawn时清理独立PGID，其他命令忽略；未把watchdog成功当作唯一清理前提。

## 代码审查结论与限制

publisher声明durable queue/exchange、persistent、mandatory、confirmed后标sent；PG行锁SKIP LOCKED并有界重试。token+expiry+attempt防陈旧写回，事务锁定刷新旧Session。intent在外部副作用前持久，未知优先于取消，不能强制盲重放。POSIX spawn/group隔离不承诺Windows；registry生产当前为空、未注册显式失败。

未实现公开job创建/analysis API或输入版本业务指纹去重；内部create_job只提供调用者事务原子性。未调用真实模型/付费服务；合成handler结果不能声称视频分析完成。未知结果对账与停止未确认的人工处理、历史分页后续另办。

## 接线后验收门槛

ARC正式main router、Alembic model import、实际OpenAPI；0003有数据→0004保留升级；整MQ节点故障、publish confirm与outbox提交间隙、真实worker死亡/watchdog/旧lease/取消停止等多进程证据；scope/完整suite无skip及最终SHA绑定。上述未完成前不标本轮done。

QA运行使用已结束并将锁归还ARC；未停止MQ节点或其他项目服务，没有远程CI/发布结论。
