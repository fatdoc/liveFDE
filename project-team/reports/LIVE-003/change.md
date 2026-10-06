# LIVE-003 本地变更单
Base: ca9de2bcd80bd224ebdc43de5ad767657e3cff90；branch: docs/LIVE-003-contracts；review head b7d4efa48ba966e55f9412102853a1e390cea98e；main集成26aaf4a。

现有10页只有Demo交互，缺少可供Python后端实现的共同契约。本变更提供操作映射、HTTP约定、数据关系和状态、JSON Schema与合成样例；不实现业务API或数据库迁移。

PM补充的日期未知与资产修订语义已纳入：started_at允许null；新待审版本保留published版本；审核指定target_revision_id；历史备播引用固定版本并提示撤回。

验证：python3 docs/contracts/check_examples.py，17个正例通过，15个负例被拒绝。该校验覆盖schema与部分证据/时间/周边界/发布指针不变量，不证明真实鉴权、事务、模型或前后端联调。正式评分为null，未调用模型。无新运行依赖，校验使用jsonschema4.26.0。

独立/root/qa_live003审查批准，详见review.md；PM-01已读取集成版本并亲自运行样例检查，最终业务核对通过。无远程PR。下一任务由BE按契约实现模块schema，再导出OpenAPI并逐步替代草案。回滚可revert本次文档提交；不涉及运行数据。每轮交付包含完成/验证/未完成/下一步及用户可发给PM的话。
