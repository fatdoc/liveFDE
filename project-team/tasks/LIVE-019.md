# LIVE-019 GitHub CI 可移植性与验收

用户授权：适配 GitHub CI 并完成验收。owner PM，ARC 独立审查。
基线：0cbd317f041be899ec49eb2faed82ea036619591。
分支 fix/LIVE-019-ci，工作副本 .worktrees/LIVE-019-ci。
范围：services/backend/tests/test_local_asr_worker.py（仅测试夹具）、.github/workflows/checks.yml、scripts/checks/、docs/operations/github-ci.md、本任务卡及 reports/LIVE-019/。

修复 Linux 下工程测试夹具依赖本机 checkout 路径的问题；保留真实资源脚本的路径、凭据、数据库和 Docker 安全限制。修复失败清理的执行条件。继续执行现有完整检查，真实失败逐项定位，不能跳过测试或降低门禁来获得绿色结果。
不改变业务功能，不调用收费模型，不开启采集，不清理历史 PR，不修改分支保护。

验收：本地工程测试和 lint；GitHub PR 全流程（结构/范围、工程测试、锁定依赖、后端 lint、前端 build/sites、FFmpeg、真实 PG/RabbitMQ 冒烟/恢复、后端集成与契约）；ARC 对最终代码 SHA 独立复核；合并后验证 main CI。
