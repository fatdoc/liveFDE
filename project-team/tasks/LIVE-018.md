# LIVE-018 首次远端完整同步

用户明确指定 https://github.com/fatdoc/liveFDE 并授权同步本地全部开发记录。owner PM，ARC 做本次窄范围独立复核；独立副本 .worktrees/LIVE-018-remote-sync，分支 chore/LIVE-018-remote-sync。

基线：本地975bcb9578a18b74bc27de27dc02a4cdce4087bc；远端2eec8af15982b28250840d0c33a1d17de12ddd65，仅Apache-2.0 LICENSE。保留双方提交，通过允许无共同祖先的本地合并与GitHub初始化PR同步，不force、不squash已有本地历史。

范围：所有本地产品Git分支及其可达提交、任务/验收/配置示例；不含runtime、真实.env/local配置、账号、模型权重、客户资料、原CPB归档和Codex聊天数据库。所有既有worktree均干净。同步前历史扫描19分支、705唯一blob，未发现配置/媒体禁入路径或所检查的密钥特征；扫描不是所有秘密不存在的形式证明。

唯一工具规则调整：允许用户远端已有LICENSE；注册一次性LIVE-018导入范围为现有合法产品根/文件，仍运行运行文件/密钥禁入检查。业务源码、迁移、依赖、capture disabled与ASR边界不改。

验收：本地结构/工程门禁、窄范围独立复核；创建PR保留审计链接；同步原始开发分支；按每个ref核对远端hash，main回到同一合并提交。GitHub Actions实际状态另报，不沿用本地通过当远程通过。
