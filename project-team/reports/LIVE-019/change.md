# LIVE-019 CI 适配变更与验收记录

基线 0cbd317f041be899ec49eb2faed82ea036619591；修复代码 7e230beb0dc9e7ad483c19b2505dafcdcfcd245e；PR <https://github.com/fatdoc/liveFDE/pull/9>。

## 变更

- 两份工程安全单测在 setUp 中替换 ROOT，addCleanup 恢复；解决 Linux/worktree 的宿主路径耦合，不改生产资源脚本。
- Workflow 的私有环境初始化步骤有明确 ID，Compose 清理仅在该步骤成功后运行；失败仍报错。
- 登记 LIVE-019 允许路径，新增任务卡及 GitHub CI 操作说明。
- API、数据库迁移、依赖锁、业务功能、采集默认开关和模型调用不变。

## 已获得证据

作者在独立 worktree 运行原有 39 项工程测试通过、完整 Ruff 通过、结构/任务范围零违规。

ARC 独立任务 01a0ff89-4e64-7242-a012-92850d916a87 于 2026-10-06 复核固定代码 SHA 7e230beb0dc9e7ad483c19b2505dafcdcfcd245e：39 项工程测试通过、scripts/checks Ruff通过、任务范围零违规、diffcheck通过。额外同进程运行两份16项测试并比较四模块 ROOT，确认全部恢复。错误checkout仍拒绝且无Docker调用；继承变量、外部context、私有文件、FIFO及错误数据库等拒绝覆盖未减。批准该 SHA 的代码与本地技术审查。

远端验收必须查看 PR 最终 head 的 Checks，以及合并后 main 的独立运行；早期失败的运行记录保留，不删除或替代。首轮远端已通过结构、工程测试、锁定依赖、Ruff、前端构建/站点测试和真实 PG/RabbitMQ 冒烟，完整后端测试仍在执行时写入本记录。最终结果、独立复核及集成 SHA 以 PR 的后续验收记录为准，不能把本节当作全部 CI 已绿。

## 边界与回滚

不代表腾讯云/本地真实模型、抖音/视频号实平台验证通过。不向CI注入生产密钥；不上传运行日志、原片或数据库。保留历史PR，本轮未处理。异常时 revert 此任务提交；不通过删除测试/continue-on-error使CI变绿。
