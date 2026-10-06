# LIVE-005 统筹集成最终独立 Review

Reviewer /root/qa_live002；2026-10-06。
候审HEAD：d4c668d17ed2cb3548a904d00b4f7765b50204aa。
**批准精确staged tree：4dfa449bb1a5c36b4c08cb2b7b93e9da07d785d9。**
结论：允许保持该树提交统筹代码，随后核对commit tree；无剩余阻塞问题。PM产品验收及done收尾另行确认，不等于远程CI/生产发布。

## 独立覆盖

审阅19个staged文件，包括main jobs router、Alembic模型注册、实际OpenAPI、套件守卫、两份多进程验收脚本、scope及资源登记、交付报告与边界。BE源码3c5ee4e已单独20项真实PG/MQ/配置通过并批准；环境修复312b647由ARC非作者审查，我在下面整条独立实跑中再次验证其MQ停启重启有效。

## 本轮独立运行

取得integration数据库及整005 MQ节点锁后，在正式main运行live005_smoke.py，**完整退出0，11项记录通过**：

- 原004管理员Cookie、场次、材料关联及原字节/hash跨迁移/重启保留；本次数据库已有0004，真实fresh=false。首次fresh=true原始证据保留Git文件，不清库或重写首次记录。
- 调用方rollback后job/outbox皆无。
- 真MQ停机后outbox保留；恢复confirm投递后再次重启MQ，持久消息仍完成。
- dispatcher publish confirm后os._exit(17)，未提交的outbox仍pending；重发后产物和revision不重复变化。
- 多次重复消息、worker重启、旧attempt消息；失败阶段retry保留已成功阶段和历史，幂等键原响应复用。
- 12秒非协作handler启动后kill父worker，3秒内实际child PID消失；lease过期重派恢复。
- 暂停旧worker、让新lease完成、再恢复旧worker；产物不被覆盖。
- 取消先请求、确认子进程不存在后canceled且无产物；未知合成付费intent恢复为不可retry安全失败。
- API重启保持状态/产物；401、CSRF403、跨workspace404成立。

结束独立确认8195关闭，日志登记的13个handler PID均无live multiprocessing.spawn进程。PG/MQ/数据保留，运行锁归还ARC，没有操作旧项目服务。仅合成处理器，没有真实模型或收费调用。

此外独立验证：
- 最新树Ruff通过、**20项工程守卫测试通过**、LIVE-005-ARC staged范围门禁0违规、diff whitespace通过。
- 契约17正例/15负例通过。
- 实际组合FastAPI schema与staged openapi.json结构完全一致：17 paths、22唯一operation IDs，重复ID告警提升error未触发。
- 读取真实完整套件JUnit：52 tests、0 failures/errors/skips，timestamp2026-10-06T00:09:38.831071+08:00。这52项由ARC跑；QA此前独立BE20项与本次整条HTTP/MQ故障实跑，不虚称重复执行过全部52项。

## 本轮统筹新增P1与修复

原suite wrapper只约束PG，而broker测试会实际消费/ACK消息，误配MQ可能操作别的队列。已要求修正：pytest前精确验证amqp/127.0.0.1/5675/live005_qa用户和vhost、拒query/fragment；CI只接受live002/5673//。本地整套入口只允许新的005 QA，避免迁移旧004库；private env需600且固定路径。

作者新增反例后独立复跑守卫测试：远程host、错端口/user/vhost、query/fragment/scheme都在subprocess之前拒绝；合法005/CI路径可进入mock pytest。P1关闭。此增量仅wrapper/测试/登记及说明，不改变已实跑的业务或smoke代码，无需重复52项/整条故障流程。

此前进程清理两项也已关闭：已死parent仍清登记worker group，setsid handler独立group根据日志登记及ps身份兜底清理；孤儿场景使用启动屏障与短于自然完成的退出断言，不依赖sleep猜测。

## 交付边界

内部create_job仅提供调用方事务原子性；公开analysis创建入口、输入版本长期业务去重、真实媒体/ASR/模型、前端接线尚未实现。生产registry空、未知调用/停止未确认保持封锁；历史无分页和人工对账后续另做。原生MQ验证不代表客户Compose部署；无remote/远程CI/PR/发布。

验证末尾write-tree仍为批准树，无unstaged差异。请原树提交后给最终SHA核对，勿将预审树047ee201作为最终批准版本。

## 最终代码提交核对

已独立核对集成提交8a34b5fb82b3385cc07dfee6728b652eaf016948的tree严格等于批准树4dfa449bb1a5c36b4c08cb2b7b93e9da07d785d9，main工作树干净。统筹代码批准正式绑定此提交；PM验收与纯文档收尾另审。
