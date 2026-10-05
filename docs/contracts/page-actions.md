# 页面与操作覆盖
以下路径均为设计中的 /api/v1；10个页面指当前8个一级路由及场次/备播详情。当前React继续用演示store，接线属于LIVE-012/013。

| 页面 | 用户操作 | 拟用接口与重要状态 |
|---|---|---|
| / | 主播/周筛选、查看待审/待备播、创建场次 | GET /dashboard?streamer_id&week_start；GET /streamers；POST /sessions；计数由服务端当前工作区计算 |
| /sessions | 搜索、平台/进度筛选、新建 | GET /sessions?q&streamer_id&platform&status&from&to&limit&offset；POST /sessions |
| /sessions/:id | 材料上传/关联、提交分析、状态/重试、逐字稿查找、来源跳转 | GET/PATCH /sessions/{id}；上传三步；POST /sessions/{id}/materials；POST /sessions/{id}/analysis-runs；GET /jobs/{id}；GET /transcripts/{id}/segments；GET /evidence/{id}；GET /materials/{id}/content |
| /reports | 单场/周报切换、日期/主播、编辑章节/正文、确认、导出预览与任务、行动带入备播 | POST /reports；GET /reports；GET /reports/{id}；POST /reports/{id}/revisions；POST /reports/{id}/confirmations；POST /reports/{id}/exports；POST /prep-plans（source_report_revision_id） |
| /weekly | 同主播自然周、来源场次、缺失清单、行动备注、报告入口 | POST /reports(kind=weekly)；GET /reports/{id}；POST /reports/{id}/revisions（weekly_notes）；自定义日期归 range_summary，不称完整周报 |
| /reviews | 筛选、看原话/回看、编辑解析/适配、批准/拒绝/撤回 | GET /assets?status=pending_review；POST /assets/{id}/revisions；POST /assets/{id}/reviews；GET /evidence/{id} |
| /library | 分类/搜索、收藏、已学习/采用标记、回看、加入备播 | GET /assets（默认 approved）；PUT/DELETE /assets/{id}/favorite；PUT /assets/{id}/usage；PUT /prep-plans/{id}/items；只引用已批准revision |
| /plans | 列表/状态筛选、创建 | GET/POST /prep-plans；空列表不制造默认计划 |
| /plans/:id | 分节/目标/时长、正文修订、拖动或按钮排序、插入资产、预览、确认、导出 | PATCH /prep-plans/{id}；PUT /prep-plans/{id}/items（全量有序条目及expected_revision）；POST /prep-plans/{id}/confirmations、/exports |
| /settings | 工作区名、审核提醒、评分/模型状态、演示重置 | GET/PATCH /workspace/settings；GET/PATCH /me/preferences；GET /settings/providers/status；评分待配置；重置示例仅Demo模式，无生产清库按钮 |

V1 审核提醒仅保存站内显示偏好，不承诺邮件/微信推送或常驻通知服务。工作区名称持久化，1～20个Unicode字符。生产端设置页显示数据库/模型实际状态，不保留“本轮演示重置”的破坏性等价功能。
报告任意日期功能保留：选择完整自然周→weekly，单场→session，其他范围→range_summary；标签必须区分，不能把任意范围伪称自然周。
阶段状态不复用Demo的review/complete/prepared作为分析job状态；场次展示进度是派生视图，附当前job/待审数/备播引用。
场次日期表单接线时增加可选开始时间与“未知”状态，默认日期精度而非午夜时间。学习库用published_revision，审核编辑latest_revision，前端不得用一份可变对象覆盖已发布内容。
