# 后端开发规范
## 代码
Python 3.11、src/live_review、类型标注、Ruff、pytest、uv 锁定；不以全局 pip 代替项目环境。
路由参数/身份/响应，service 业务事务，adapter 外部交互，worker 薄调度。配置集中 Pydantic Settings。
测试 fixture 与真实 provider 显式区分，生产禁止失败自动返回假数据。
日志 request_id/job_id/stage/attempt，遮蔽密钥、cookie、签名 URL、敏感全文；异常可诊断不泄漏堆栈。
输入验证+DB 约束，参数化查询；UTC 与毫秒统一，未知 null。
subprocess 参数数组，无 shell=True，超时/退出码/资源限制；文件 key 不使用用户任意路径。

## 数据
ORM/Pydantic schema 分开；每请求/任务 Session 独立；service 定事务边界。
审核/修订 expected_revision 条件写，幂等唯一约束，不能只靠先查有没有。
Alembic 唯一建表通道，不用 create_all 代替迁移；BE 协调单 head。
扩展兼容迁移优先；非空先回填，破坏性修改有备份恢复，不 DROP 掩盖失败。
事务/约束/迁移在真实 PG 测试，SQLite 不能代替；测试 DB 不碰用户/其他窗口数据。

## 模型
provider 保存来源/配置/prompt/schema/耗时/可得费用；prompt 语义变化升版本。
输出 schema+证据引用校验；原话与原文核对；抽样不冒充全程理解。
报告、周报、教学解析、备播是不同任务；无自动批准权限。
不从单场推断稳定性格或成交效果，不复制竞赛权重。

## 测试和交付
unit：状态机、修订冲突、引用、时间/周边界。
integration：鉴权/文件越权/Range/finalize、PG 约束迁移、outbox 重复、worker 中断恢复。
provider：固定响应契约测试，真实调用另列 smoke，不在常规 CI 消耗额度。
E2E：实际文件→报告→审核→备播，浏览器检验；构建不代替体验。
测试覆盖业务失败，不镜像实现凑数量；不删断言/假成功解决错误。
交付 API/迁移/配置影响、命令真实结果、未测/兼容/恢复；缺样本/账号明确列出，不阻塞独立基础工作。
