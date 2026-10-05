# LIVE-004 已实现接口与设计边界

本轮仅实现管理员身份、主播/场次、材料；原React Demo仍使用演示数据，未接后端。正式身份/场次/材料schema以Python模块和从FastAPI导出的openapi.json为准。draft.schema.json仍仅描述后续分析/报告/审核等设计及合成样例，不是另一个生产schema。

| 已实现 | 范围 |
|---|---|
| /api/v1/auth/login、me、logout | 管理员CLI初始化、Cookie持久会话、Origin/Fetch-Metadata/CSRF、限流、安全错误 |
| /api/v1/streamers | GET分页列表、POST创建；平台douyin/wechat/other，无平台抓取 |
| /api/v1/sessions、/{id} | GET分页/详情、POST创建、PATCH版本修订；from包含/to不含；未知时间null，duration_ms为null，processing_status初始pending |
| /api/v1/materials/uploads、/{id}/content、/{id}/finalize | 初始化幂等、流式接收、格式/大小/hash校验、失败恢复、租约隔离、按工作区blob去重 |
| /api/v1/materials/{id}、/{id}/content | 可用材料元数据、授权GET/HEAD；单Range206/416，HEAD忽略Range返回完整metadata，无原始私有路径 |
| /api/v1/sessions/{id}/materials | POST关联/重复幂等；GET分页材料列表供重启后找回；PDF只能reference |

未实现：workspace settings/preferences、dashboard聚合、分析/任务、报告、资产审核、学习库、备播及导出、模型状态/评分、平台采集。没有多角色RBAC；管理员是唯一产品角色，主播是业务对象。

上传说明：首版允许MP4/WAV/MP3（ffprobe真实解析且禁止网络协议）、UTF-8纯文本（上限10MiB）、未加密可解析PDF（上限20MiB），总体上限可配置，默认512MiB。没有续传，失败可整文件重试；expired返回410。客户端原始文件名仅展示，不作为磁盘路径。语音/画面分析未启动，任何材料均不自动成为主播原话证据。临时失败文件保留便于恢复，自动过期清理尚未实现，必须单独安排保留策略。

认证说明：先用受控CLI建管理员，无默认口令/公开注册。浏览器发送HttpOnly/SameSite Cookie；生产必须HTTPS与Secure。变更接口带可信Origin与X-CSRF-Token（从login/me获取）。OpenAPI导出用于结构对齐，以上运行时会话/CSRF规则同样必须遵守。

生成方式：从app执行 `uv run --project services/backend python scripts/checks/export_openapi.py`。不运行数据库或模型即可导出声明schema；导出成功本身不算接口验收，真实证据见project-team/reports/LIVE-004。
