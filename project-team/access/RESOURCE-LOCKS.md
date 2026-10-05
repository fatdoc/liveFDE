# 共享资源
本表是调度记录，不是硬隔离。
| 精确路径/资源 | owner | 任务 | 基线/开始 | 释放条件 | 状态 |
|---|---|---|---|---|---|
| app 存量目录搬迁、frontend/prototype→web、ignore/入口文件 | ENG-01 | LIVE-001 | 无首次提交 | staged 审查完成并交接 | 已释放，代码基线 1366573 |
| app/.git index/HEAD、LIVE-001 状态与评审记录 | ARC-01 | LIVE-001 | 无首次提交 | 首次提交及 worktree 验证完成 | 完成，收尾记录提交后释放 |
| localhost:5188 Demo 预览 | ARC-01 | LIVE-001 | frontend/web PID69984 | PM验收后统一安排下一任务 | 保留预览，不抢占 |
需登记锁文件/迁移head/OpenAPI/生成客户端/共同配置/端口/DB。开始认领，交接明确释放，不抢其他窗口资源。
