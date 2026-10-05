# LIVE-005 ENG 环境变更单

Owner /root/be_live004a（本轮转岗ENG），base 8cc9ea5，branch chore/LIVE-005-environment。仅五个授权文件，主app未改；独立review待执行。

新增固定PG Compose、原生MQ及安全生命周期脚本、资源守卫测试和操作说明。任务be/qa/integration/qa_identity均获独立数据库、MQ vhost、queue名与storage；600凭证在runtime/live-005。

实测：7项unittest pass；Ruff pass；四角色真实SQL连接与MQ publish/consume pass；BE越权QA数据库和MQ vhost拒绝；MQ真实stop后连接失败、start后恢复publish/consume；重复up保留既有环境。RabbitMQ实际4.2.3；PG本地已有固定digest镜像。测试非mock业务，未调用模型。

启动第一次PID归属校验发现Homebrew beam命令行不含node与mnesia路径，安全拒绝后核实进程并改为beam + 本轮runtime已打开文件校验，再以独立cookie指定node进行CLI操作；未kill未知PID。中文runtime路径导致Rabbit CLI非致命unicode诊断噪声，实际退出码和AMQP均成功，限制已记操作文档。

最终保留PG15450/MQ5675、25675运行。故障窗口需ARC协调，用脚本mq-stop/mq-start/mq-restart；pg-stop仅本轮容器，所有停止保留数据。共享主机EPMD不管理、不终止。旧资源未改。

未验证：005业务迁移、worker/dispatcher/outbox、真实模型和客户Compose部署。该交付只证明环境与隔离，不是LIVE-005完整业务验收。回滚代码可revert；运行停止用精确命令，不删runtime与凭证。
