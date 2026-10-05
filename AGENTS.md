# 直播复盘与资产工作台：开发总则
生效：2026-10-05，用户最新决定优先于旧 CPB/模板说明。
- 必读 docs/README.md、04-directory-contract.md、09-git-rules.md 和当前任务卡。
- Python/FastAPI + React/TypeScript + PostgreSQL，独立部署，不连接原 CPB 服务、账号或数据库。
- 唯一新后端 services/backend/（后续实现）。现有前端 frontend/web/，已由 prototype 迁入；不新做第二套 UI。
- 旧 backend/、ai-scoring/、frontend/{admin,user,teacher}/ 等 CPB 副本已移至工作区 archives/cpb-reference-20261005，只读参考；原 CPB 与客户资料只读。
- 一任务、一 owner、一分支、一 worktree。没有首次提交前不启动并行 worktree。先完成 LIVE-001。
- 只修改任务允许路径；目录、契约、依赖锁、迁移 head 由统筹协调。明确路径 git add，检查 staged diff，不提交他人成果。
- 作者不能最终批准自己的代码。独立 Review 绑定 head SHA，新代码使受影响的结论失效。
- 无远程时使用本地变更单，不声称已建 GitHub PR 或启用分支保护，不伪造身份。
- 原话、教学解析、适配稿分开；仅已审核固定资产版本进入正式学习库/备播引用。
- 评分维度未定，正式分为 null/待配置，不用竞赛规则、演示数字替代。
- 不编造时间戳、模型结果、测试、审核人或完成状态；真实失败必须呈现。
- 密钥、客户原片、数据库、模型权重、日志不入 Git。临时文件清理与原始资料保留分开。
- 模型调用限任务授权的配置和预算；结果未知的付费请求不盲目重放。
- done 需要集成 SHA 与适用验收；合并、发布、客户验收分别记录。
当前状态以 project-team/STATUS.md 为准；规范不是已实现功能。

## 用户对话与工作区（2026-10-05 补充）
所有项目模块及后续 worktree 均放在上级“直播体系FDE”下，worktree 使用 ../.worktrees/<task-id>-<role>/，不采用工作区外的默认代码工作副本。
PM-01 是用户统一对话入口；其他员工通过任务消息协作，不把日常技术问题直接抛给用户。见 docs/13-window-collaboration.md。
