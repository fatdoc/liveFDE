# LIVE-024 解析修复与真实复验

基线ddcfb9745dbaa78a47cf44b10efb9921ed412af3；固定实现676c4398f2bd4163c0c24278a1d62d145ae54f3f。Owner ARC，ENG-02实现，QA-02非作者独立审查。PR https://github.com/fatdoc/liveFDE/pull/15。

## 已完成与证据

未配置Cookie时不再发送空格，也不使用上游内置Cookie；只有显式非空本机配置进入最终请求。上游吞异常时仍返回固定白名单分类，原始响应/异常/临时流URL/Cookie不进入错误记录。

QA-02在固定676c439独立审查通过，独立隔离PostgreSQL选集109 tests、0 failures/errors/skips（123.83秒），证据runtime/live-024/live024_suite_d164e916c24c4f0d979e2e673094cd63。原报告runtime/live-024/qa-fixed-review.md仅本机保存，含具体用户来源，公开仓库仅记录此审查摘要。作者同选集109通过、42工程检查、Ruff/scope通过；代码版远程CI 37488414982与37488424204均success。文档最终head的合并/CI闭环留runtime/live-024/closure.json。

确认应用live020没有活跃采集/任务/pending capture outbox后，旧API25919/executor25920正常退出，新API34403/executor34405运行已审676c439，前端25921仍用023已审UI。实际策略未变：仅抖音、HTTPS、douyincdn.com、60秒/50000000字节；原策略规范化指纹50551a6e0fe29bf9108dbe72446ba6f61cb285746968059ed8b30fbeff0ba9f2。交接runtime/live-024/handoff.json。无模型下载/云调用/新依赖/迁移。

## 真实复验结果：失败，原因已明确到空响应

用户提供并授权同一房间；ARC通过实际前端只点击一次新录制，2026-10-06T15:39:46Z创建，15:39:48Z任务failed，error_code=source_empty_response。handler35608已确认stopped，没有manifest/material，未执行ASR。运行前已保存三条原失败基线；所有失败记录保留，不以新结果覆盖旧失败。

证据runtime/live-024/{before-retry,real-retry}.json、real-retry.png及runtime/live-020/logs/executor-live024.log；来源及原始业务ID留本机，不发布到公开仓库。此结果说明新错误分类实际生效，不能声称平台录制成功；也不能仅凭空响应判断必须登录、下播或风控。没有再次盲目重试、扩大CDN或降级HTTP。

## 原仓库对照与下一条件

已只读核对同一固定上游README/main/parser/stream/http client，见upstream-audit.md。原库配置读取Cookie且parser有内置默认值；没有配置不等于没有Cookie。我们的数字房间解析路径相同，但原main对抖音还优先FLV、H265回HLS，目前封装直接record_url的HLS偏好尚未对齐；不是此次解析阶段空响应的已证原因。

PM统一确认用户正常浏览器是否可播放，以及正常登录/会话接入条件；不要求Cookie/密码贴聊天。合法会话配置及FLV兼容性作为明确后续项；不能绕平台验证或直接复用上游历史Cookie。本轮工程修复完成，真实平台能力仍未通过。回滚：无活跃任务后drain，再以023副本重启API/executor，前端/策略/数据保留。
