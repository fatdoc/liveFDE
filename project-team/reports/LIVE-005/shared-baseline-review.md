# LIVE-005 共享基线独立 Review

Reviewer /root/qa_live002；2026-10-05。
批准精确staged tree：6560fefd4880618c3b2a0a6d19284dc0340a9227。
范围仅5个staged文件：config.py、test_job_config.py、repository.py任务scope、STATUS、RESOURCE-LOCKS。未跟踪live005_smoke.py不属于本次批准。

初审发现dispatcher间隔float允许NaN/inf，会破坏等待行为。作者已改Field(gt=0,allow_inf_nan=False)并加入两个回归；当前独立5测试通过，Ruff、LIVE-005-ARC staged范围门禁0违规、diff whitespace通过。

生产环境禁止job_test_handlers，lease正数校验；BE/ENG/ARC写范围分别注册，QA资源明确15450/5675/25675与专属DB/vhost/storage。本次只批准共享配置与分工基线，不能作为jobs/outbox/worker实现或真实依赖验收通过。提交应保持同树，业务实现另待最终SHA审核。
