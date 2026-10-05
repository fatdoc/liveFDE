# Git / Review / PR
## 当前事实
LIVE-001 启动时（2026-10-05）：app/.git 存在，feat/cpb-live-fork 无提交、跟踪文件 0、remote 为空。外层不是仓库。当前提交/审查状态以 project-team/STATUS.md 和 LIVE-001 交付记录为准。
旧 master/模板 origin 文档已失效；本轮未建远程或分支保护。
LIVE-001 保全整理后创建 main 首次本地提交。bootstrap 无法走不存在的 PR，应先独立审查文件清单/本地 diff 再提交，例外留记录。

## 分支与环境
main 稳定，无长期 develop；feat/LIVE-004A-auth、fix/LIVE-xxx-description、docs/LIVE-xxx-description。
一任务一 branch/worktree/owner，记录绝对路径、base SHA、端口、DB/Compose project、存储卷；不同窗口不能迁移同一开发数据库。
worktree 不复制脏文件；先保全 Demo。主 checkout 统筹与串行集成，不多个窗口 git switch。
worktree 绝对路径必须在 /Users/docfat/Desktop/个人/project/直播体系FDE/.worktrees/ 下，命名 <task-id>-<role>。本地 git worktree add 指定该路径；不要使用会把代码放到工作区外的默认托管 worktree。首次提交前仅允许统筹串行写主 checkout。
共享文件认领唯一持有人；冲突回原作者，不整文件覆盖。
不得未授权 force push/reset --hard/clean -fd，不代提交别人文件，不全库格式化。

## 提交
feat(materials): LIVE-004C add finalized uploads。
明确路径 git add；检查 status/staged diff、敏感数据和体积，rename 检查两端。
身份用真实 Git 配置，角色记任务，不伪造作者身份来模拟多位审阅者。

## PR 或本地变更单
有远程：Draft→自检→Ready→独立 Review→QA→合并，使用 .github/pull_request_template.md。
无远程：project-team/reports/LIVE-xxx/change.md，记录 base/head 和 diff，称本地变更单，不称 GitHub PR。
包括问题/结果、任务/路径、API/迁移/prompt/依赖、测试证据、风险、回滚和未测。
Review 记录独立窗口/任务 ID、base/head SHA、覆盖、问题、验证和结论。新代码使受影响审批失效；更新主分支后如有行为变化重新验证。
P0/P1 阻止合并；P2 修复或 ARC 说明豁免理由与跟进任务；纯风格建议不阻塞。

## 合并门槛
范围/结构合规；独立批准；认证/迁移/跨模块/规则有 ARC 技术结论；适用测试/构建通过；唯一迁移 head；契约/客户端一致；无密钥和原片；阻塞评论解决。
ENG 串行合并，默认 squash，记录任务 head 和 main 最终 SHA；集成版本跑受影响冒烟，失败暂停队列修复/revert。

## 远程门禁
组织/仓库/可见性待指定，建议私有，不能推到 CPB 或模板仓库。
配置后 main 禁直接推送/强推，要求 PR、真实可批准 reviewer、适用 checks、解决评论、更新复审。
多个 AI 窗口共享同一 GitHub 账号不能互相满足平台独立批准；保留本地独立证据，实际平台批准需真实授权审阅者。不能宣称已有硬隔离。
CODEOWNERS 填真实账号，不填 PM/BE 编号；它是审阅路由，不是写权限防火墙。
LIVE-002 建 CI：结构/敏感文件、Ruff/pytest、前端类型/构建、迁移/契约；文档-only 链接一致性。不用空检查冒充通过。
LIVE-002已配置 .github/workflows/checks.yml，可在本地运行等价检查；业务契约合成样例纳入条件检查。未配置远程或CODEOWNERS，也没有远程CI执行/分支保护证据。

## 发布
合并不自动发布。QA 验收、ARC 技术就绪、PM 范围确认，按用户已有授权 ENG 执行版本标签/发布说明/备份恢复。
清理分支/worktree 前保全未提交文件并确认已集成，不删其他窗口资源。
参考：[分支保护](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[Review](https://docs.github.com/en/pull-requests/reference/pull-request-reviews)。
