# LIVE-005 统筹集成与故障验收

状态：统筹真实验收通过，待统筹代码独立review及PM最终核对。用户授权限任务与失败恢复，不扩展006/前端/付费或外部发布。

## 执行与版本
| 实际执行任务 | 交付 | 独立审核 |
|---|---|---|
| /root/eng_live002 本轮BE-01 | 3c5ee4ed33fba8bc1bcfa1dcc2227cb9d3ebf66f；jobs/workers/0004/API | /root/qa_live002：20真实PG/MQ/配置测试，无skip；review.md |
| /root/be_live004a 本轮ENG-01 | 24028ba环境；312b647修复MQ重启判定 | ARC-01非作者审查；environment-review.md |
| /root 技术统筹 | 正式main/jobs路由与Alembic注册、OpenAPI、套件入口及多进程故障脚本 | 最终精确tree另由QA批准 |

这些是实际子任务，不是额外侧栏窗口或后台常驻员工。PM入口仍为直播FDE｜PM-01｜产品与需求。工作区和worktree均留在直播体系FDE内。

共享配置cd85a6e的生产禁用合成handler/有限正数轮询周期已经独立批准；环境main8cb3700，业务main0c4dcb6，环境修复maind4c668d。统筹最终集成SHA由批准树提交后记录，不把作者源码提交冒充正式接线完成。统筹故障脚本按资源/进程管理（live005_smoke.py）与有顺序依赖的场景断言（live005_scenarios.py，480行）分开；后者超过300行已检查职责，只承担本轮验收，没有业务实现或通用工具堆叠。

## 真实检查与证据
- 正式组合应用全套：52 passed、0 skipped、0 failure/error，runtime/live-005/pytest-results.xml。覆盖既有004与新005。保留已知Starlette/httpx弃用警告。
- Ruff通过；原15工程门禁通过后，MQ生命周期增量独立10项（原7+新增3）通过；最终新增入口PG/MQ守卫2项后，总工程门禁20项。契约17正例/15负例按预期通过。
- 实际OpenAPI导出17个路径；0004_jobs唯一迁移head，真实PG alembic check没有模型差异。
- 原始首次升级见fresh-upgrade-results.json：空库升0003，CLI管理员+HTTP主播/场次/文本材料上传及关联，再升0004；同cookie、场次、关联、原材料字节和SHA256保留。首次true记录未被后续false覆盖。
- 最终整条脚本退出0，11项场景见integration-results.json。后次复跑因数据库已有0004如实fresh=false，没有清库/降级伪造首次升级。

## 多进程故障结果
使用真实PG15450、原生RabbitMQ5675、独立API8195、独立Celery solo进程及受控handler子进程。处理器全部合成，没有真实视频分析、供应商网络或付费调用。
1. 调用方事务rollback后job和outbox均不存在。
2. 关闭真实MQ，投递失败保留outbox并退避；恢复投递后再重启MQ，持久消息仍被worker完成。
3. publisher confirm后、outbox事务提交前直接os._exit(17)，PG outbox仍pending；再次投递不重复修改业务产物/任务revision。
4. 同消息多次发送、重启worker后任务状态与产物不变。
5. 第二阶段失败后带revision+幂等键retry，保留第一阶段产物及旧attempt错误；旧attempt消息失效，同键异请求409。
6. 12秒不合作handler已启动取得PID后仅SIGKILL父worker，3秒内确认child PID消失；租约过期重派后完成。
7. 暂停旧worker进程组至lease失效，新worker完成后恢复旧worker；旧执行不能覆盖新产物。
8. 30秒不合作handler取消先202请求，随后确认子PID不存在才接受canceled，产物未落库；终态重复取消200。
9. 合成付费intent先写PG，再kill父worker；恢复failed/call_result_unknown、can_retry=false、retry409，重复消息仍只有一个intent。
10. API重启后状态/原产物保持；无登录401、缺CSRF403、不同workspace读取和取消404。

## 实际发现与修复
- 最终预审发现套件入口仅检查PG而未限定MQ，新增真实broker测试可能误消费错误vhost。已在pytest启动前精确限制broker协议/host/port/user/vhost且拒绝query/fragment，新增不允许启动pytest的反例；本地套件只接受005专库，CI独立002端点另明确。
- 配置NaN/Infinity轮询间隔被独立审查发现，改Field拒绝并增加测试。
- 取消必须确认处理进程停止；预审修正无法join时普通stage_failed错误，改execution_stop_unconfirmed禁止retry。
- retry清旧错误不利于审计，增加typed attempt_history同事务快照；合法skipped和reason保留。
- 第一次完整故障跑发现MQ立即重启误把TIME_WAIT/退出过渡当端口占用；source312b647改安全重绑探针并等待原进程和监听关闭。独立真实TCP测试通过，ENG连续两次真实重启保留消息，统筹最终完整场景通过。

## 边界与下轮
原React前端仍Demo；尚无公开analysis-runs/任务创建入口、媒体抽取/ASR/视觉/报告/资产/备播。create_job只提供事务基础，业务输入版本幂等由未来分析入口负责。生产handler注册表为空，未注册明确失败；合成handler生产配置禁止。
当前attempt历史无分页；未知调用结果/停止未确认封锁自动retry，人工核对和解除流程后续单独设计。POSIX进程组支持macOS/Linux，不声称Windows执行器已验证。原生MQ验证不等于客户Compose部署验证。无remote/远程CI/PR/发布。
优先下一轮LIVE-006媒体抽音频与ASR适配；真实模型账号/预算需明确，不自动启动该任务。
