# LIVE-005 本地隔离环境

本轮环境由 ENG 建立，业务任务实现及独立验收另由 BE/QA 交付。固定工作区 `/Users/docfat/Desktop/个人/project/直播体系FDE`，不复用 LIVE-002/004 或原 CPB 数据。

| 资源 | 固定目标 |
|---|---|
| PostgreSQL | Compose project `live-fde-005`，container `live-fde-005-postgres-1`，127.0.0.1:15450 |
| PostgreSQL image | `postgres@sha256:f1c3376c26f2609ab9f29f71f824103fe2fcd8ee0346485cb6122a4f93df6f94`（本机已有16系列） |
| RabbitMQ | 本机 Homebrew 4.2.3，node `live005@localhost`，127.0.0.1:5675，distribution127.0.0.1:25675 |
| 数据配置日志 | `runtime/live-005/postgres`、`runtime/live-005/rabbit-native` |
| 私有配置 | `runtime/live-005/private.env`，600；任务env亦600，目录700 |

RabbitMQ没有复用旧节点，也没有安装全局后台服务。Erlang EPMD 是主机级发现服务，不由本脚本停止。管理插件关闭，无新管理HTTP端口。原生MQ仅本机验收，不能据此声称客户Compose部署已验收。

## 启停与故障验证

在本项目 checkout 下执行：

```sh
python3 scripts/checks/live005_environment.py up
python3 scripts/checks/live005_environment.py mq-stop
python3 scripts/checks/live005_environment.py mq-start
python3 scripts/checks/live005_environment.py mq-restart
python3 scripts/checks/live005_environment.py pg-stop
```

`up` 幂等保留PG角色/数据库/凭证；运行中的本轮MQ做定向诊断后保留。`mq-stop`/`mq-restart`影响本轮所有owner，必须由ARC协调窗口后执行。停止用独立cookie认证的 `rabbitmqctl -n live005@localhost stop`，事前核对本轮PID为beam进程且打开本轮runtime文件；不接受任意PID、node或路径。PID复用/外部进程、被占端口、runtime符号链接、未知私有env字段或更改DSN均拒绝。不全局kill，不删数据，不执行down -v。PG停止同样校验项目label及数据挂载，恢复用up。

脚本不接受环境里的 `DOCKER_*`、`COMPOSE_*`、`RABBITMQ_*`、`ERL_*`、LIVE_RUNTIME、PG_PASSWORD、MQ_COOKIE覆盖；验证当前Docker为本地unix endpoint并固定该endpoint。私有数据读取不打印值；RabbitMQ定义使用加盐SHA256哈希，密码不放命令参数。脚本职责为这一个开发环境的安全配置及生命周期（按PG/MQ/守卫函数划分），不扩成通用运维框架。

若创建角色中途失败、凭证丢失、容器归属不匹配或启动超时，保留现场交ENG核查，禁止删env/库绕过守卫。启动失败不会强杀未知进程。

## 任务隔离

| owner | 数据库/登录角色/MQ用户/vhost/queue名 | 私有文件 | storage |
|---|---|---|---|
| BE | live005_be | runtime/live-005/be.env | runtime/live-005/storage-be |
| QA | live005_qa | runtime/live-005/qa.env | runtime/live-005/storage-qa |
| ARC集成 | live005_integration | runtime/live-005/integration.env | runtime/live-005/storage-integration |
| QA旧身份基线 | live005_qa_identity | runtime/live-005/qa_identity.env | runtime/live-005/storage-qa_identity |

每个env包含 LIVE_DATABASE_URL、LIVE_BROKER_URL、LIVE_STORAGE_ROOT、LIVE_TASK_QUEUE。最后一个提供各自队列名，BE需在Celery配置读取或启动时传对应队列；即使同名queue，不同vhost也不能互相消费。角色只获自己vhost权限；PG撤销PUBLIC CONNECT。各窗口只迁移自己库；qa_identity不跟随未来迁移，用于历史身份基线测试。

用dotenv或Python按首个`=`解析写入进程环境；路径包含空格，不能直接source。勿打印URL、cookie或密码。项目凭证位于runtime，不入Git。

## 已完成工程验证与边界

- 7项资源守卫测试、Ruff通过。
- 四组真实PG连接与各自MQ发布/消费成功；BE凭证访问QA数据库及MQ vhost被拒绝。
- 已执行真实MQ停止，AMQP连接确实失败；原数据目录重启后发布/消费恢复。
- 幂等up再次验证保留已有角色/凭证，无重置数据。最终保留本轮PG与MQ运行，供BE/QA继续。
- 旧5432/15432/15440/5188与旧MQ节点未停止、未重配。尚未执行业务worker/dispatcher故障恢复、005迁移或客户容器部署；这些不由本报告冒充通过。

官方机制参考：[定义文件启动导入](https://www.rabbitmq.com/docs/definitions)、[密码哈希](https://www.rabbitmq.com/docs/passwords)、[运行目录变量](https://www.rabbitmq.com/docs/relocate)。本机CLI针对中文路径有unicode转换诊断噪声，退出码、节点就绪及真实AMQP结果均已验证；不得单凭CLI文字判定业务成功。

## 2026-10-06 MQ 重启竞态修复

集成smoke在真实AMQP连接后复现：node已停止，但启动探针对25675普通bind返回占用。原因是TIME_WAIT与真实listener未区分。现探针使用SO_REUSEADDR（不用SO_REUSEPORT），TIME_WAIT可重绑、活listener仍拒绝。停止在首次确认归属后定向认证stop，并同时等原PID退出/僵尸及5675、25675均可重绑；不再在关机收缩fd时把已确认进程误判为外部进程。

新增真实临时TCP listener/TIME_WAIT回归和停止等待顺序、占用拒绝测试，共10项通过。随后在本轮独立integration vhost发布durable queue与delivery_mode=2消息，连续两次实际mq-restart，首次读取requeue、第二次读取ack，均核对原payload后仅删除本测试专用queue。恢复完成后保留MQ运行；未删除其他队列/数据。
