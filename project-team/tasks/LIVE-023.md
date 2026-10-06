# LIVE-023 抖音就绪修复与明确阻塞

用户连续要求启动采集并反馈未就绪。Owner ARC-01，fix/LIVE-023-readiness，.worktrees/LIVE-023-readiness，base a9ca92cec7f8bcded7c44e20d7ba3a6121c75744。QA-02负责非作者静态防御/代码审查，不重放此前被自动安全检查中止的探针、变体或外网请求。

精确范围：capture模块readiness/router/service、provider健康说明、对应capture tests；前端CapturePanel/types及交互验收；scope/本卡/状态/资源锁/报告/docs capture与契约。无新迁移/依赖/评分。先准确区分服务在线、平台依赖、取流域策略；native新建门禁与health一致，旧幂等/停止/导入可恢复。不得仅设依赖路径把空域策略伪装成可录。

本轮复用runtime/live-020，ARC串行接手PM启动的executor17106；变更前查active/queued/outbox并正常drain，旧环境不动。依赖可只读复用015已固定版本。有限真实试录必须有明确非作者就绪结论；静态审查不冒充动态出站隔离验收。用户不配置环境，尚无具体直播样本。

ARC范围补充：ENG-02在同一工作副本仅编辑capture relay/recording/policy/resolver和test_capture_resolution.py，交ARC统一提交；DNS受监督超时/停止与HTTPS限制属于本轮确定阻塞修复。root负责其他路径；QA-02固定SHA独立复核。首轮runtime仅douyin、HTTPS、窄域、60秒/50MB，未获真实源不声称平台通过。
