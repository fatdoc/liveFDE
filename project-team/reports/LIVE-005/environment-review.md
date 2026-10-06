# LIVE-005 工程环境独立 Review
Reviewer ARC-01（/root）；作者/root/be_live004a。
批准 source SHA 24028ba；基线8cc9ea5。
独立审查固定资源、凭证600、runtime符号链接拒绝、Docker本地endpoint固定、PG归属/mount检查、MQ本轮PID与打开文件验证后cookie定向node停止、vhost隔离；无未知进程kill、无删除库/卷。
独立运行7项资源守卫测试通过、main新版owner门禁0违规。独立以4个owner凭证逐一真实PG current_user与真实MQ发布/消费通过，仅新exclusive auto-delete测试队列。初次审查脚本错误用了Queue.get(timeout=3)，修正为库支持的get()后实际通过；此脚本错误未修改生产代码。
MQ停止/恢复与跨owner拒绝由作者实测，未声称本人重复操作。业务多进程故障验收由统筹后续完成。允许按此SHA本地串行集成，不等于LIVE-005业务验收或客户部署。

## MQ重启故障增量复审
正式集成故障跑复现mq-restart在成功停止后误报25675占用，runtime/mq-restart-diagnostic.log保留。修复source312b6474c6cdceb4a4ccb6dd1b463e14019590a7：SO_REUSEADDR探针允许TIME_WAIT重绑但不使用SO_REUSEPORT；停止需已认证原PID退出且两个端口均可重绑。ARC独立审查diff并实际运行10项测试通过（含真实本机TCP listener/TIME_WAIT回归），批准集成；连续两次真实MQ重启和原持久消息保留由ENG实测，统筹完整故障链随后继续。没有删除节点数据或放松外部进程保护。
