# LIVE-015～017 协调登记独立审查

独立QA /root/qa_live001；仅审main基线61c2cbb当前未提交登记，不审采集实现、不运行平台、不启动端口/数据库。

已核对：实际worktree .worktrees/LIVE-015-capture在61c2cbb，分支feat/LIVE-015-capture；任务卡明确CAP独占模块与所列共享接线、ARC仅台账/集成。现有迁移revision确为0005_asr_settings，因此规划0006_capture down_revision正确。文档明确拟端口启动前复查、无真实平台/投屏/ASR新增付费证明，不冒称实现或验收。十五至十七提前执行不把007～014标启动。

P2待处理：
1. CAPTURE_SCOPE给出整个services/backend/tests/，比任务卡test_capture*.py及对应fixture宽，可能放行无关身份/ASR测试。建议限制capture测试/fixture范围，必要旧测试变更单独登记。
2. RESOURCE-LOCKS末尾仍写006C ARC独占共享pyproject/uv.lock等，没有CAP当前接手记录；建议追加当前015～017共享owner及资源状态，避免台账冲突。

本轮不需要任何真实平台测试；待上述修正/ARC明确豁免后可批准协调登记提交，后续实现必须绑定新SHA独立审查。

## 修正复核：批准协调登记

已复核更新工作副本：CAPTURE_SCOPE改为6个明确capture测试/fixture和tests/capture子树，无整个tests授权；RESOURCE-LOCKS明确006C代码锁已释放、预览资源仍保留，并登记CAP唯一共享作者、ARC台账/集成责任、拟端口/独立库/磁盘预算。独立git diff --check通过。两项P2关闭，批准本次协调登记增量提交；仅范围/责任登记，不构成未来采集实现批准。下一次实现审查须绑定CAP具体SHA。
