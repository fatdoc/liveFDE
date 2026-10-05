# 数据、约束与状态 draft-1
这是建模设计，不含实际DDL或Alembic revision；实现交BE。数据业务模块只在实际代码出现时创建，禁止空壳。

## 公共列与关系
UUID主键、workspace_id、created_at/updated_at UTC；更新聚合有revision>=1；外部ID只作映射。跨工作区FK必须由(workspace_id,id)复合唯一/外键或等价强校验防护。
用户属于默认workspace；session属于streamer；session_material连接材料；transcript_revision属于material；segment属于transcript_revision；evidence引用固定segment/frame/页；analysis_run输入快照引用固定材料及转写版本；report_revision固化run与evidence集合；asset_revision固化原话来源；prep_revision固化asset_revision。

| 表组（拟名） | 关键字段/约束 |
|---|---|
| admins、auth_sessions | username规范化unique；password_hash；session token_hash unique/expires_at/revoked_at；禁明文token |
| workspaces、user_preferences | name/timezone；(user_id,workspace_id)unique；review_reminders；各自revision |
| streamers、live_sessions | session.streamer_id与同workspace FK；session_local_date必填；started_at可空、time_precision/date或minute或second、time_source；duration_ms nullable>=0；媒体探测时长不手编 |
| blobs、materials、session_materials | blobs(workspace_id,sha256)unique；material目的/原文件名/metadata；关联(workspace,session,material,role)unique；同文件关联不同场次不冲突 |
| uploads | owner、声明大小、received_size、受控temp_key、expires_at、status、lease；不能把暂存当正式文件 |
| transcript_revisions、segments、frames | transcript(material,revision)unique；segment(transcript_revision,ordinal)unique；segment start/end均null或end>=start>=0；frame实测timestamp>=0；immutable |
| jobs、job_steps、attempts、outbox | job幂等指纹；attempt(job,number)unique；stage产物引用；outboxevent_id unique；lease token/expires/heartbeat；dispatcher可重发 |
| analysis_runs、evidence_items | 输入文件/模型/prompt/schema/rule快照；evidence来源不可变；JSON结构外再检引用存在 |
| reports、report_revisions、report_sources | revision(report,number)unique；kind/streamer/时间边界；来源session/run/transcript/report版本固化；缺失原因集合 |
| assets、asset_revisions、review_events | revision(asset,number)unique；聚合revision并发token、latest_revision_id与published_revision_id分开；原话/teaching_notes/adapted_script独立；事件actor/action/from/to/revision/reason |
| favorites、usage_events | favorite(user,asset)unique；usage(user,asset_revision)unique或幂等upsert；不冒称销量 |
| prep_plans、prep_revisions、prep_items、prep_asset_refs | revision(plan,number)unique；item(revision,item_id)和(revision,position)unique；scheduled_local_date必填、scheduled_at可空及time_precision；source_report_revision_id可空；refs固定asset_revision |
| idempotency_records | workspace/actor/method/route/key unique；request_hash/response_ref/expires_at；不能保存密码请求body |

所有索引先服务明确查询：workspace+session_local_date、streamer+session_local_date、asset状态/分类、job状态+lease。V1关键词参数化ILIKE，后续真实慢查询再索引优化，不先建向量库。
删除采用明确归档/撤回，不级联删被报告/备播引用的证据。临时upload过期和原始材料保留策略分开；首版无“重置真实数据”。

## 状态机
- upload：pending→receiving→uploaded→finalizing→available；接收失败failed可重新PUT；finalize失败failed并保留可恢复信息；expired不可续用。available重放finalize返回同material。
- job：queued→running→succeeded/failed/cancel_requested；queued可cancel_requested；cancel_requested→canceled/failed/succeeded（外部已完成的竞态需记录）；failed经合法retry回queued且attempt+1。
- stage：pending/running/succeeded/failed/skipped/canceled。仅成功持久产物才能succeeded；skipped必须有理由。部分ASR丢段整体失败或明确partial产物，不能标完整成功。
- asset revision：draft→pending_review→approved/rejected；approved→withdrawn。rejected再次编辑生成新待审版本；批准版本内容不可原地改。
- report revision：draft→confirmed；人工改或重新分析生成新的draft；旧confirmed保留。
- prep revision：draft→ready；编辑产生新draft；引用撤回使ready有效性在读取/确认时标warning或阻止重新确认。

并发审核必须在同事务锁定/条件更新资产revision并写review_event；两个approve不能生成两个发布结果。job领取token隔离旧worker写回，外部调用不持有长事务。确认/撤回/导出都再次鉴权，用户界面disabled不是权限措施。

## 证据与三类文字
transcript_quote必须绑定已有segment，quote是对应原文的原样连续摘录（生产实现需校验对应片段；本轮fixture采用整段原文以避免未定义offset语义）；不允许让模型改写后仍叫原话。
start_ms/end_ms均未知时为null，seekable=false，仍可定位文字段；两个值中只填一个非法。frame观察仅timestamp，不伪装转写发言。
PDF reference只作reference_document(page>=1)，可定位页但seekable=false，不能直接形成“主播原话”资产。若PDF内引用口播，仍需关联真实transcript证据独立核对。
无证据只能出hypothesis/待核验建议，evidence_ids=[]且limitation必填；不得出fact或quote。没有观测依据不能制造成效/长期人格结论。
资产quote、teaching_notes、adapted_script三字段独立，学习库和备播引用必须是approved revision；建议不自动变成资产。

## 周边界与覆盖
weekly默认Asia/Shanghai，周一00:00到下周一00:00，左闭右开；2026-09-28周的UTC边界为2026-09-27T16:00:00Z至2026-10-04T16:00:00Z。
按session_local_date归属；若已知started_at，必须与其在Asia/Shanghai的日期一致。同场跨午夜不拆成两场；仅知道日期时started_at=null，不补00:00伪造实测。来源快照保留time_precision/time_source，周报按日期范围查而非用虚假时间排序。同一天未知时间场次按稳定ID顺序而非假定先后；本版只计所选主播。
来源集合包括范围内全部未归档场次的ID；included只取可用分析run/转写版本，excluded带pending/failed/no_material/no_analysis原因。部分来源可生成并标coverage=partial，零可用来源422；不能把缺失当零分。
included和excluded均保留streamer_id/session_local_date/started_at/time_precision/time_source/timezone；校验同主播、日期在所选范围。快照固定session revision/analysis_run/transcript_revision；源修改后status=stale但不篡改旧报告。重跑新报告revision，保留人工作品可比较。
range_summary允许任意非空日期范围，UI明确“日期范围总结”；不能当成标准周报或跨规则可比较成长趋势。

## 后续实现验收矩阵
事务并发审批/排序冲突、跨工作区文件ID、授权前Range探测、重复投递和旧lease、同hash重复关联、部分ASR失败、未知定位、周末边界、PDF误作原话、撤回后旧备播、报告修订确认失效均需BE集成测试。
本轮的fixture校验只提供可执行合同样例，不替代上述真实DB/API验收。
