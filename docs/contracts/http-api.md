# HTTP API 设计 draft-1
所有业务路由 /api/v1，未实现。仅 LIVE-002 工程 /health/live、/health/ready 另列实际实现；不把下表当已部署能力。

## 通用协议
JSON UTF-8；UUID；RFC3339 UTC存储；定位整数毫秒/未知null。列表 {items,total,limit,offset}，limit默认20最大100，确定性排序 created_at desc,id desc。
错误 {code,message,request_id,details}：details只可读安全字段，不带密钥/路径/堆栈。400无效语义，401未登录，403已知权限/CSRF失败，404不存在或非本工作区对象，409版本/状态/幂等冲突，413过大，415类型不支持，422字段结构，429限流，503依赖不可用。
敏感响应 Cache-Control: private,no-store。文件读权限先于Range/ETag/长度判断，未授权不能探测媒体存在。浏览器同源Cookie，不把登录令牌放URL。
所有PATCH/修订/审批/排序请求 required expected_revision（正整数），条件更新成功revision+1；过期409，details含current_revision及可访问对象链接，保留客户端草稿。该JSON协议不用If-Match，以免两套冲突优先级不明。

## 身份、设置、场次
| 方法 路径 | 请求字段 | 响应/效果 |
|---|---|---|
| POST /auth/login | username,password | 200 user{id,display_name,role,workspace_id},csrf_token；轮换服务端会话，设置HttpOnly/SameSite=Lax cookie，生产Secure |
| POST /auth/logout | 无body，CSRF | 204，使会话立即失效 |
| GET /auth/me | — | user和csrf_token；无会话401 |
| GET/PATCH /workspace/settings | PATCH {expected_revision,name} | {id,name,revision,timezone}，timezone首版固定Asia/Shanghai |
| GET/PATCH /me/preferences | PATCH {expected_revision,review_reminders:boolean} | {revision,review_reminders} |
| GET /settings/providers/status | — | {items:[{kind,configured,availability,checked_at,model_label}],scoring:{score:null,reason:rules_not_configured}}；不含密钥、完整地址或原始错误 |
| GET/POST /streamers | POST {name,platform,platform_ref?:string} | 201 Streamer；无账号爬取行为 |
| GET /dashboard | streamer_id?,week_start=YYYY-MM-DD（周一） | {period,counts,recent_sessions,weekly_report_id:null或UUID}，无报告不伪造摘要 |
| GET/POST /sessions | POST {streamer_id,title,platform,session_local_date,started_at:null或RFC3339,time_precision:date或minute或second,timezone} | 201 Session{id,revision,streamer_id,title,session_local_date,started_at,time_precision,duration_ms:null,processing_status} |
| GET/PATCH /sessions/{id} | PATCH {expected_revision,title?,streamer_id?,session_local_date?,started_at?,time_precision?} | Session；修改影响已出报告时旧报告保留输入快照并标过期 |
| GET /sessions | page-actions中的筛选 | List<Session>；空列表total=0 |

登录入口无现成CSRF时严格Origin/Fetch-Metadata校验同源及速率限制，已有会话状态变更再校验X-CSRF-Token；登录失败统一401不泄漏用户名。会话只存哈希token，停用管理员/退出立即拒绝。CLI引导管理员，无公开注册或默认口令。
workspace来自服务端身份，客户端不能以任意workspace_id越权；跨workspace外键引用由服务和复合约束双检。
现有新建场次仅日期：生产表单增加可选开始时间和“精确时间未知”，不能静默补00:00。date要求started_at=null；已录分钟/秒时保存带时区值且与session_local_date一致，另记time_source=user_entered或media_metadata。日期归属用于周报，不将它当录像时间锚点。

## 上传、关联与读取
1. POST /materials/uploads，Idempotency-Key 必填；{filename,byte_size,media_type,purpose:session_media|transcript|reference_pdf,sha256?} →201 {upload_id,status:pending,max_bytes,expires_at}。filename只展示。
2. PUT /materials/uploads/{upload_id}/content，原始字节body，Content-Length与声明匹配；临时受控key流式落盘，未完成不登记可用material。首版不续传，重试从头覆盖本upload暂存，互斥lease保护同upload。
3. POST /materials/uploads/{upload_id}/finalize，幂等 →200 {material_id,status:available,sha256,size_bytes,deduplicated}。探测真实格式/大小/哈希；失败有明确错误，清理临时不会删除原材料。
4. POST /sessions/{id}/materials {material_id,role:primary|reference} →201关联，重复同关系200 {already_linked:true}，不可凭hash探测其他工作区文件。
5. GET /materials/{id} →可用元数据；GET/HEAD /materials/{id}/content →鉴权流。
后台上限配置明确，不能只有前端限制；拒绝任意URL下载。输入声明与ffprobe/解析结果不符返回415/422。文件内容完成标记原子写入，finalize与DB失败可恢复。

内容响应：无Range 200，合法单区间 bytes=0-99/open-ended/suffix 支持206，Content-Range、Content-Length、Accept-Ranges:bytes；完全越界416并带 bytes */size。多区间首版忽略Range返回完整200，不伪装multipart；语法非法400。HEAD无body但正常元数据；零字节文件不作为可用媒体。
If-Range强ETag不匹配返回完整200，不返回旧部分；ETag来自内容hash。用户不可见/未登录先404/401，不返回size。
参考：[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)，这是本项目明确的支持子集。

## 分析、任务与证据
| 方法 路径 | 请求 | 响应 |
|---|---|---|
| POST /sessions/{id}/analysis-runs | Idempotency-Key；{material_ids,vision_enabled,prompt_version,rule_version:null或已配置ID} | 202 {analysis_run_id,job_id,status:queued} |
| GET /sessions/{id}/analysis-runs | — | 历史输入快照/状态/产物ID列表 |
| GET /jobs/{id} | — | {id,revision,status,current_stage,attempt,progress:null或实测,steps:[{stage,status,reason}],error:null或安全错误,can_retry,cancel_requested} |
| POST /jobs/{id}/retry | Idempotency-Key；{expected_revision,from_stage} | 202 原job新attempt；非法阶段409 |
| POST /jobs/{id}/cancel | {expected_revision} | 202 cancel_requested；终态返回200终态，无重复供应商调用 |
| GET /sessions/{id}/transcripts | material_id? | 版本列表 |
| GET /transcripts/{id}/segments | q?,limit,offset | List<Segment>；搜索返回原segment_id和原始定位 |
| GET /evidence/{id} | — | Evidence及解引用来源；无法定位时seekable=false |

ASR chunks全局偏移统一毫秒，start/end同时已知或同时null。并非所有转写都能定位；未知的文本证据可以读原段，但不能显示视频跳转。
幂等键作用域(workspace,actor,method,route,key)，保存规范化请求hash、结果对象ID；至少保留24小时，分析的输入版本+配置唯一指纹另在DB长期去重。相同key同请求重放原响应，相同key不同请求409 idempotency_conflict；事务先claim键，不能靠进程字典。
后台任务的duplicate delivery另由job/attempt领取租约和业务唯一键防重；不是HTTP幂等能替代队列幂等。

## 报告与资产
| 方法 路径 | 请求 | 响应/效果 |
|---|---|---|
| POST /reports | Idempotency-Key；{kind:session|weekly|range_summary,streamer_id,session_id?,local_start?,local_end_exclusive?,timezone} | 202 {report_id,job_id}；weekly强制自然周，无可用来源422 no_analyzed_sources |
| GET /reports、/{id} | kind/streamer/date过滤 | list或{current_revision,body,source_snapshot,coverage,status} |
| POST /reports/{id}/revisions | {expected_revision,summary,strengths,issues,actions,weekly_notes,visible_sections} | 201新revision，确认状态失效，保留模型原稿与人工稿 |
| POST /reports/{id}/confirmations | {expected_revision} | 200固定报告revision确认事件 |
| POST /reports/{id}/exports | Idempotency-Key；{report_revision_id,format:markdown|pdf} | 202 {export_id,job_id}；默认仅确认版本，未确认要求明确draft=true并加水印 |
| GET /exports/{id} | — | {status,material_id:null或UUID,error}；下载仍走鉴权content |
| GET /assets | status默认approved、category,q,streamer_id,favorite,limit,offset | List<AssetRevisionView>，候选/拒绝不混入学习库 |
| GET /assets/{id} | — | 当前内容/版本与历史可访问引用 |
| POST /assets/{id}/revisions | {expected_revision,teaching_notes,adapted_script,conditions,cautions,category} | 201待审revision；不修改原话或证据 |
| POST /assets/{id}/reviews | {expected_revision,target_revision_id,action:approve|reject|withdraw,reason?} | 200状态/review_event；拒绝/撤回reason必填 |
| PUT/DELETE /assets/{id}/favorite | — | 204；按用户/资产幂等 |
| PUT /assets/{id}/usage | {learned,adopted,asset_revision_id} | 200；主观记录非成交归因 |

资产原话由可核对transcript evidence形成；若纠错需材料/证据修订链，不用普通资产编辑改原话。PDF参考不得伪造口播引文，见数据规范。
资产聚合GET同时返回revision（并发token）、latest_revision_id、published_revision_id及对应状态。编辑已批准资产只更新latest_revision_id，新待审稿不能覆盖published_revision_id；学习库默认返回published版本。审批请求另必填target_revision_id，校验属于该asset与expected_revision，避免误批另一个草稿。
批准新版本原子切换published指针；旧版本内容仍approved但superseded=true，历史备播固定引用继续可读。新加入计划只选当前published且未撤回版本；完整保存既有计划时不把未改变的旧引用当新增。撤回当前published置null，不自动回退到更早版本，学习库下架；撤回历史版本使对应旧稿提示并阻止再次确认ready。
报告actions为结构化[{id,text,owner,verification,evidence_ids}]；说明无证据时assertion_kind=hypothesis并声明限制。周报备注为人工字段，不因模型重跑覆盖。

## 备播
GET/POST /prep-plans：创建{title,streamer_id,scheduled_local_date,scheduled_at:null或RFC3339,time_precision:date或minute或second,timezone,source_report_revision_id?}→201 {id,revision,status:draft,items:[]}。
GET/PATCH /prep-plans/{id}：PATCH{expected_revision,title?,scheduled_local_date?,scheduled_at?,time_precision?}。
PUT /prep-plans/{id}/items：{expected_revision,items:[{id,title,minutes,goal,body_doc,interaction_prompt,asset_revision_ids}]}，items数组顺序为权威，ID唯一；有序全量更新同事务，409保留本地草稿。
body_doc是限制节点的Tiptap JSON（段落/文本/粗体/斜体/列表），后端拒绝未知节点/危险URL，不接受任意HTML脚本。预览/导出统一安全渲染。
POST /prep-plans/{id}/confirmations：{expected_revision}→ready；新编辑回draft。确认要求至少一个环节、每个环节有非空标题和非空可见正文，minutes为正整数；不强制引用资产，但引用存在时须合规。确认时重查所有引用，撤回/未审409 asset_not_approved，不能静默替换。
POST /prep-plans/{id}/exports：同报告异步导出模式，固定plan_revision。
旧计划读取保留原asset_revision_ids及引用快照，另附 current_status/withdrawal_warning；撤回不会抹掉旧稿，但禁止将其新加入计划或重新确认就绪。

备播时间与场次采用相同精度规则：仅选日期时scheduled_at=null，不补午夜；有时间时必须与scheduled_local_date和Asia/Shanghai一致，计划日期不是实际开播证据。
