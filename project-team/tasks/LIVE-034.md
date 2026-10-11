# LIVE-034 模型测试正常关闭连接误报修复

PM授权最小修复、离线/真实loopback测试、独立审查、CI与部署。base35835e2，fix/LIVE-034-model-check，.worktrees/LIVE-034-model-check；ARC作者、QA非作者审查，runtime/live-034保留记录。

只读确认2026-10-11 13:51/13:52两次新测试为unknown/llm_result_unknown；历史记录没有底层异常，不能从记录认定某个具体原因。本机运行Python3.11，真实本地HTTPServer完整200+Content-Length+Connection:close复现read1耗尽响应后下轮settimeout报EBADF；Python3.10行为不同。

修复完整响应结束后不再操作已关闭transport；保持时限、最大响应、截断/chunk trailer校验、TLS/DNS策略、无自动重试。新增类别与阶段日志只包含本地枚举，不记录异常原文/URL/headers/key/body；页面使用稳定错误码提示。

所有测试仅合成数据和本机loopback/socketpair，不调用真实模型。保持13:51/13:52及旧unknown/tombstone，不改变用户配置、不自动新建真实测试；上线后若要新的一次合成测试须另有用户明确授权。无迁移/依赖变化，契约字段不变。实际模型能否成功仍待实测。
