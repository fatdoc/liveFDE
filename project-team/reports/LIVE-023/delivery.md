# LIVE-023 限定试录准备完成

代码基线a9ca92cec7f8bcded7c44e20d7ba3a6121c75744；实现214b8ed93fcbf33448f1771fe09fb59b77da503b。ARC作者/串行集成；ENG-02负责有界解析子任务；QA-02非作者审查批准，详见qa-review.md。PR https://github.com/fatdoc/liveFDE/pull/14；此记录时远程CI仍运行，未宣称已合并，最终远端与集成记录留runtime/live-023/closure.json。

## 已验证

- 固定实现独立70 tests，0 failures/errors/skips；日志/JUnit在runtime/live-023/live023_suite_dcb5970513da4684a6e4e06c72a75905。
- Ruff/结构scope通过；42工程tests、4 hosting tests、前端类型/构建通过；OpenAPI快照相等。保留既有构建大chunk提示与TestClient弃用提示。
- Edge mock API浏览器契约：空来源策略阻止启动并说明原因、失败修正/未知重试幂等、刷新恢复、停止确认、导入、材料手动离线ASR和视频号指引通过；不是实平台录制。
- 实际UI5199/API8199/PG15500，用户已有“测试”场次58b46bf3-f294-418f-9ac5-11f0206badab显示配置已就绪与60秒/50MB；合法格式输入使按钮启用，随后清空，没有提交伪造房间录制。

## 实际运行交接

2026-10-06 23:15 Beijing，确认live020数据库/用户身份、active_capture/active_jobs/pending_capture均0；停止旧API、drain旧executor，再停旧Vite。保留策略备份runtime/live-020/config/capture-policy.before-live023.yaml，不删媒体、DB或旧失败记录。

新API PID25919、executor25920、UI25921均使用LIVE-023已审代码。记录在runtime/live-023/handoff.json；启动时源树干净。实际生效策略：enabled=true、native、allowed_platforms=[douyin]、https_only=true、stream_domains=[douyincdn.com]、max_seconds=60、max_bytes=50000000；依赖复用runtime/live-015固定DLR add187f8d8c7ff7d231fcbee45cbb4f1ed247d3a。未下载权重、调用云模型或启动真实取流。

实际policy SHA256=50551a6e0fe29bf9108dbe72446ba6f61cb285746968059ed8b30fbeff0ba9f2；executor binding=420dd295a5450c39d138049a99d3f4f4ae020119013c8521d5af998789c881ca。鉴权health证明execution.ready=true、douyin.start_ready=true、wechat.start_ready=false、real_platform_verified=false。详见runtime/live-023/{runtime-health,active-binding}.json及output/playwright/actual-ready.png。

## 下一步与边界

用户只需提供自有或授权正在直播的抖音PC数字房间链接，统一由PM接收；不要求用户配置环境。第一轮一次短试录，核对关闭、导入、播放结果；尚无样本所以未开始、未宣称真实成功。未知CDN/HTTP明确失败，不自动放宽。视频号本轮未开放，需后续单独技术就绪和手机验收。

独立批准仅限已知授权来源的小范围试录，不是动态出站隔离认证或生产发布。首次历史ASR停止未确认根因仍未修复，本轮没有重试它。回滚需先无活动任务、drain并恢复备份策略与旧版本服务，不删除现有数据。
