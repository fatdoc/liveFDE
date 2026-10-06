# LIVE-022 固定集成版本独立后端验证

非作者验证：/root/qa_live002。
固定SHA：bc9a891a27141f9e006206fed91f4722a585817b；运行前后HEAD一致且工作树干净。
结论：此固定版本后端现有套件通过，cursor修正与本轮三份文档契约差异批准；可作为后端集成门禁证据。前端浏览器、真实平台、客户部署和专项安全验收不在本报告批准范围。

实际执行：services/backend/.venv/bin/python scripts/checks/live020_acceptance.py --all。
独立新库及证据目录：runtime/live-020/evidence/live020_suite_c52f299d628647ad87bc88305bf00543。
结果：returncode0；JUnit与日志均为361 tests、0 errors、0 failures、0 skipped；耗时554.44秒。仅1条已有Starlette/httpx弃用提示。
此命令明确排除test_jobs_broker.py，因此不能称本轮完成真实MQ验收。未使用应用库，未修改源码或应用配置。

只读契约复核：
- docs/contracts/openapi.json与当前app.openapi()结构完全相等（本地导出比较，无启动HTTP服务）。新增GET capture/runs的session_id/limit1..100/cursor max512与router一致。
- docs/contracts/implementation-status.md准确列出直播场次与材料/采集/手动ASR接入，其他业务仍演示；native仅消费capture_v1，真实平台与完整出站隔离待验收，未把实现等同实平台通过。
- docs/README.md新增原生联调文档入口，目标文件存在。
- 74319c9的cursor修正先校验JSON对象和session_id/created_at/id三字段字符串类型，再检查session归属、带时区时间和UUID；错误统一invalid_cursor422。新增[]/null/空对象/字段数值或对象/无时区/跨session回归在本次361套件内通过。

边界：仅运行明确授权的正常现有套件；没有另行运行此前被自动安全检查中止的探针，也没有换工具重放。通过不是实平台网络隔离结论。
