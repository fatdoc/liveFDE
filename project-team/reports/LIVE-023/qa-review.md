# LIVE-023 固定版本独立复核

- Reviewer：QA-02（/root/qa_live002），非本轮代码作者。
- Base：`a9ca92cec7f8bcded7c44e20d7ba3a6121c75744`
- Head：`214b8ed93fcbf33448f1771fe09fb59b77da503b`
- 工作副本：`/Users/docfat/Desktop/个人/project/直播体系FDE/.worktrees/LIVE-023-readiness`
- 复核后 HEAD 一致，git status --short 无输出。未修改代码或运行配置。

## 结论

此固定 SHA 未发现阻塞本轮有限试录的缺陷。先前初始 DNS 可绕过录制时限/停止的 P2 已关闭。独立批准本轮代码的有限技术就绪：在下列候选策略实际生效、执行器版本及配置指纹核实后，可以对用户自有或已获授权的明确抖音房间进行一次有限试录。该结论不是动态出站隔离认证、真实平台已通过、生产发布批准或任意不可信媒体的安全保证。

候选策略只读复核：`runtime/live-023/capture-policy.candidate.yaml`；当前文件含 enabled=true、execution_mode=native、allowed_platforms=[douyin]、https_only=true、stream_domains=[douyincdn.com]、max_seconds=60、max_bytes=50000000，输出在 runtime/live-020/captures，解析器路径只读复用 runtime/live-015。候选文件存在不等于已生效。域规则覆盖该后缀允许的子域，并非单一主机固定列表。未知 CDN 或 HTTP 必须保持拒绝，不自动放宽。尚无明确房间样本，不声称已完成真实录制。

## 复核范围及依据

已复核本轮完整差异（18 文件），包括 capture policy/recording/relay、readiness/router/service、前端启动门禁及健康提示、浏览器契约 fixture、任务/文档/范围记录和对应测试。

- 初始 Relay 之前开始共享录制 deadline；初始解析、子清单与重定向沿用该期限。
- DNS 使用可终止子进程，单次上限与共享期限取较小值；轮询停止、finally 终止和回收，无法确认回收时明确失败。loopback bind 避免隐式反向 DNS。
- HTTPS 限制在目标解析之前执行，覆盖初始目标、HLS URI 与重定向；兼容默认值未被误认为严格运行策略。
- 既有域后缀、所有解析地址公网检查、固定实际连接 IP、HTTPS 证书/主机名验证和重定向重新校验保留；FFmpeg 读取 loopback capability URL，HLS 严格白名单与 URI 重写保留。
- 健康接口和 native 新建采用一致的 readiness 门禁，在线 executor 不等于可采集；已有幂等结果、停止和导入可恢复；禁用平台不能通过 operator 或 probe 绕过。
- UI 对缺失 readiness fail closed，区分配置就绪与真实源未验证。本次 UI 独立复核为静态代码审查，未独立运行浏览器验收。

## 独立验证

通过本工作副本 backend venv 执行 `runtime/live-023/check-selected.py` 一次；使用新建隔离数据库与既有本地环境，运行 readiness/executor/recording/resolution/API/import/providers 七组用例。

实际结果：**70 passed，0 failures，0 errors，0 skipped**，57.379 秒。独立读取 JUnit 验证 tests=70，非仅依赖 shell 返回码。唯一 warning 为 Starlette TestClient/httpx 弃用提示，不影响本次结果。

证据：
- `runtime/live-023/live023_suite_dcb5970513da4684a6e4e06c72a75905/pytest.xml`
- `runtime/live-023/live023_suite_dcb5970513da4684a6e4e06c72a75905/pytest.log`

新增 resolver 用例使用本地模拟命令/替身，覆盖超时、停止、强杀回收、共享初始/清单 deadline、HTTPS 首跳/HLS/重定向拒绝、混合公私网地址拒绝及关闭中断。它们不等于真实 DNS/平台或动态出站边界验证。

## 启用与验收边界

1. ARC 按现有流程串行 drain，确认无活动/待执行采集后切换固定代码及上述策略，并记录实际执行器 SHA/配置指纹和 health 门禁结果。
2. 仅在得到明确授权房间后试录；60 秒预算包含录制阶段初始媒体 DNS，前置房间解析、结束封装/导入有各自边界，不声称整个请求墙钟时间必小于 60 秒。
3. 真实验收需另留来源、成功或失败状态、时长/体积、停止结果、成品可探测和导入证据。失败如实返回，不通过放宽协议或域策略掩盖。
4. 本次没有发起外部请求或网络探针，没有重放或变形执行此前被自动检查中止的探针。本地合成结果不替代该尚未取得的验证证据。
