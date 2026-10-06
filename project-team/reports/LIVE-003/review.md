# LIVE-003 独立 BE/QA Review

- Reviewer：独立子任务 `/root/qa_live003`，非作者；2026-10-05。
- base：ca9de2bcd80bd224ebdc43de5ad767657e3cff90。
- head：6d017ca6f3ab7aabc3be97762ba2be7d4fbfe97e。
- 范围：任务允许路径、契约全部文件、现有 React 10 路由和关键操作源码对照；未修改产品文件。
- 运行：`python3 docs/contracts/check_examples.py` → 17 valid / 10 invalid PASS。
- 结论：暂不批准，以下 P2 需作者修复或 ARC 显式豁免并跟进；无 P0/P1。属于设计草案，不要求此轮实现业务 API。

## P2-1 任务并发 token 缺失，HTTP 与 Job schema 不一致
`docs/contracts/http-api.md:44-46`：retry/cancel 强制 expected_revision，但 GET /jobs 返回不含 revision。`draft.schema.json` 的 Job 也没有 revision 且 additionalProperties=false，添加 revision=1 会被拒绝。HTTP 声明 steps，schema 同样拒绝 steps。客户端无法依据草案完成无冲突重试/取消。应统一 GET 响应、schema、样例，至少提供 revision，并确定 steps 的最小结构/语义。

## P2-2 备播创建日期无法无损映射，ready 条件遗漏现有业务
`http-api.md:79-83` 要求 scheduled_at，而 `frontend/web/src/pages/Plans.tsx` 创建只收 date，报告转备播也只产生 date。场次已解决日期未知，但计划未定义日期精度/null，接线容易静默补午夜。应明示计划日期+可选时间及响应字段。PlanEditor 仅当所有环节填写才允许 ready，而契约仅写资产状态校验；补明非空环节与有效正文的服务端 ready 条件（否则空 items 或空正文可确认）。

## P2-3 周报来源快照 schema 无法表达文档要求的时间来源
`data-and-states.md` 明确快照保留 time_precision/time_source、按 session_local_date 归属。ReportSnapshot.included 的 closed schema 只有 session_id/session_revision/run/transcript IDs，不能携带这些字段，样例也缺；没有来源日期无法验证集合属于所选周。补来源时间字段/主播归属或明确可解引用的不可变时间快照结构，并增加跨周或错主播负例。SessionTime 也可补 time_source，以便交接时保持一致。

## P2-4 证据来源绑定语义假阳性
`check_examples.py:24-29` 仅检查 segment_id 对应 source_revision_id/quote/times，没有检查 source_id 对应来源。独立试验：将 known_transcript_evidence.source_id 改为 99999999-9999-4999-8999-999999999999，validate 仍通过。source_segments 注册表没有 source_id，无法排除把正确原话挂到另一个文件。建议注册材料映射、验证 source_id 并加入负例；不要求构建生产 DB 校验。

## P2-5 自然周校验放行非午夜微秒
`check_examples.py:49-51` 只检查 hour/minute/second，没有 microsecond。将 weekly 样例两端分别改为 2026-09-27T16:00:00.500Z 和 2026-10-04T16:00:00.500Z，validate 通过，违反自然周左闭右开边界。比较完整本地午夜值或同时检查 microsecond，补负例。

## 已确认的边界
- 10 路由均列出主操作；工作台、上传/分析、逐字稿、报告编辑/确认/导出、周备注、审核、收藏/学习、备播编辑/排序、设置均有映射。
- 未登录/跨工作区文件先鉴权；Range/ETag/尺寸不能先泄漏；cookie/CSRF/Origin、安全错误明确。
- HTTP 幂等与队列租约防重分开；分析输入版本指纹长期保留。
- 资产 latest 与 published 分开；目标审批版本显式传入；新草稿不下架旧版，历史固定引用与撤回语义明确。
- 原话、教学解析、适配稿分开；PDF 不当口播；未知定位 null；评分保持 null。
- 未声称真实后端/事务/外部模型已实现；实际独立校验仅针对草案与合成样例。

## 修复复审：批准

- 新审查 head：`b7d4efa48ba966e55f9412102853a1e390cea98e`；base 不变。
- 本节取代首轮“暂不批准”的结论。逐项核对 6d017ca → b7d4efa diff，原 5 项 P2 均已解决，无剩余阻塞项。
- Job 在 HTTP/schema/正例中均含必需 revision 与 steps；缺 token 负例被 schema 拒绝。
- 备播支持 scheduled_local_date + nullable scheduled_at + time_precision；明确不补午夜、至少一环节、非空标题/可见正文/正整数时长方可 ready。
- included/excluded 来源快照均保存日期、时间精度与来源、主播和时区；语义校验覆盖日期范围与主播归属。
- source_id 已与 source_segments 注册值绑定；周边界新增 microsecond 检查。
- 独立运行：`python3 docs/contracts/check_examples.py` → PASS，17 个正例、15 个负例。
- 独立额外检验：逐个确认新增 5 个负例由相应条件拒绝；周开始 2026-09-28 与最后一天 2026-10-04 正例通过，excluded 中 2026-10-05 被拒绝。
- 批准范围仅此契约草案提交；不代表业务 API、鉴权、事务或模型能力已经实现/验收。未改产品源码、未提交、未合并。
