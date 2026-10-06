# 已实现接口与设计边界（LIVE-004～017基础）

已实现管理员身份、主播/场次、材料；LIVE-005增加任务与恢复基础设施，最终验收状态见任务看板。LIVE-006C将现有React的ASR设置/登录/试用接到后端，其余页面仍演示数据。正式身份/场次/材料schema以Python模块和从FastAPI导出的openapi.json为准。draft.schema.json仍仅描述后续分析/报告/审核等设计及合成样例，不是另一个生产schema。

| 已实现 | 范围 |
|---|---|
| /api/v1/auth/login、me、logout | 管理员CLI初始化、Cookie持久会话、Origin/Fetch-Metadata/CSRF、限流、安全错误 |
| /api/v1/streamers | GET分页列表、POST创建；平台douyin/wechat/other，无平台抓取 |
| /api/v1/sessions、/{id} | GET分页/详情、POST创建、PATCH版本修订；from包含/to不含；未知时间null，duration_ms为null，processing_status初始pending |
| /api/v1/materials/uploads、/{id}/content、/{id}/finalize | 初始化幂等、流式接收、格式/大小/hash校验、失败恢复、租约隔离、按工作区blob去重 |
| /api/v1/materials/{id}、/{id}/content | 可用材料元数据、授权GET/HEAD；单Range206/416，HEAD忽略Range返回完整metadata，无原始私有路径 |
| /api/v1/sessions/{id}/materials | POST关联/重复幂等；GET分页材料列表供重启后找回；PDF只能reference |
| /api/v1/jobs/{id}、/{id}/retry、/{id}/cancel | 持久任务状态与安全错误、带revision的失败阶段重试及幂等、取消请求与执行停止分开 |
| /api/v1/asr/settings、/health、/transcriptions、/transcriptions/{id} | 工作区持久设置/revision、就绪、真实本地文件任务与结果；腾讯真实调用待凭证/预算 |
| WS /api/v1/asr/stream | 鉴权PCM流、partial/final/completed、安全结束与不可重放；WS不在OpenAPI paths中 |
| /api/v1/capture/health、/probe、/runs、/runs/{id}、/stop、/import | 统一采集基础、状态与停止、已关闭媒体导入及场次关联；默认关闭，仅完成本地合成验收，真实平台/手机及出站隔离复核待完成 |

未实现：ASR以外的workspace settings/preferences、dashboard聚合、业务分析入口、报告、资产审核、学习库、备播及导出、正式评分。平台采集仅基础代码已实现并默认关闭，不代表抖音/视频号真实接入已验收；当前不启动试录。没有多角色RBAC；管理员是唯一产品角色，主播是业务对象。

上传说明：当前允许MP4/WAV/MP3/M4A/AAC（后两种由LIVE-006C加入，ffprobe真实解析且禁止网络协议）、UTF-8纯文本（上限10MiB）、未加密可解析PDF（上限20MiB），总体上限可配置，默认512MiB。没有续传，失败可整文件重试；expired返回410。客户端原始文件名仅展示，不作为磁盘路径。LIVE-006由操作员显式提交抽音/转写；上传不自动开始分析，任何材料均不自动成为主播原话证据。临时失败文件保留便于恢复，自动过期清理尚未实现，必须单独安排保留策略。

认证说明：先用受控CLI建管理员，无默认口令/公开注册。浏览器发送HttpOnly/SameSite Cookie；生产必须HTTPS与Secure。变更接口带可信Origin与X-CSRF-Token（从login/me获取）。OpenAPI导出用于结构对齐，以上运行时会话/CSRF规则同样必须遵守。

生成方式：从app执行 `uv run --project services/backend python scripts/checks/export_openapi.py`。不运行数据库或模型即可导出声明schema；导出成功本身不算接口验收，真实证据见project-team/reports/LIVE-004。

任务边界：create_job是供未来业务入口调用的内部事务函数，创建job/阶段/outbox不自行提交；调用方须将业务记录一并提交，并负责业务输入版本的唯一性。LIVE-006C已通过ASR入口创建限定类型任务，仍没有任意公开创建任务或analysis-runs接口，不声称已实现同输入长期去重。retry接口的幂等和重复消息的租约保护已分开实现。阶段产物为受限JSON存入PG；成功阶段与有理由的skipped阶段在重试时保留。progress目前null，不伪造视频处理百分比。

LIVE-006注册media.extract/media.asr处理器，由本地受控操作员CLI提交；ASR须显式YAML配置，网络默认拒绝，生产禁止离线fixture。原005合成fixture处理器仍仅开发显式开启；未注册处理器明确失败。任务取消先返回cancel_requested；只有受控处理子进程确认停止才记录canceled，无法确认停止保持安全失败。供应商调用前先持久化intent，未知结果阻止自动重放；本轮没有实际模型或付费调用。006已增加FFmpeg抽音/分段、音轨全局时间戳、离线fixture及audio/transcriptions兼容传输协议；没有公开analysis-runs创建入口，也未接前端。完整manifest/转写存于受控文件，任务阶段仅保存哈希引用和摘要；部分转写保留证据并失败。不能把fixture当作真实识别结果。真实服务商、识别质量和计费未验。

LIVE-005相对旧草案增加typed attempt_history：重试前的attempt、安全错误、各阶段状态/reason和受限JSON产物快照同事务保留，可通过GET任务查询；当前没有历史分页。真实多进程验收与交付边界见project-team/reports/LIVE-005/integration.md。

006配置/媒体/任务入口、真实本地与模拟协议的证据边界见 [LIVE-006 验收入口](../ai/live006-acceptance.md)。YAML公开快照固定在任务输入，密钥仅执行内存解析；配置漂移拒绝重试，预算美元值是授权声明，未实现厂商精确计费。评分、长期画像与报告仍未实现。
