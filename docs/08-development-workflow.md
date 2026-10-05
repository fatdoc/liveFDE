# 工作流程与审批
任务状态 backlog→ready→in_progress→review→verified→done，另有 blocked。ready 有唯一 owner、路径、依赖、reviewer、验收；done 需集成 SHA，不等于发布。
阻塞记原因/负责人/解除条件；失败回 in_progress。状态放任务卡和 STATUS，不靠聊天记忆。

| 动作 | 决定者 | 是否找用户 |
|---|---|---|
| 范围内实现、修复、测试、任务分支提交 | 执行者 | 不重复询问 |
| 新目录、公共接口、迁移、依赖 | ARC + owner | 技术内部协调 |
| 普通合并 | 独立 Reviewer + 适用 QA，ENG 执行 | 不逐 PR 询问 |
| ARC 自己写代码 | 对应 owner 独立 Review + QA | ARC 不自批 |
| 产品范围、评分标准、交付承诺 | 用户，PM 提供具体方案 | 无已有决定时 |
| 破坏性生产操作、超预算付费、对外发布 | 依据用户明确授权 | 无授权时提出具体结果/影响 |
| 远程组织/仓库/可见性 | 用户指定，ENG 配置 | 未指定才问，不阻塞本地 |

独立技术批准必须来自另一窗口/任务，作者换岗位名不算独立 Review；没有 reviewer 保持 review，不伪造 verified。
用户不逐文件审批；开发审批与系统内话术审核分开。

流程：PM 拆验收→ARC 冻结边界→ENG 准备隔离 worktree→owner 实现自检并提交→独立 Review/QA→ENG 串行合并→PM 业务核对→发布另记。
共享写资源在 project-team/access/RESOURCE-LOCKS.md 认领。迁移 head 由 BE 协调；锁文件 ENG 刷新；客户端 FE 统一生成。
所有角色先是规划，首次基线前一个窗口整理。依赖 fixture 标注，不冒充接通。
