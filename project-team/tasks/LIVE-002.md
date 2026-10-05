# LIVE-002 后端工程骨架与门禁
- 状态：done；owner ENG-01；独立 reviewer /root/qa_live002。
- 依赖：LIVE-001；base ca9de2b；branch feat/LIVE-002-foundation。
- 工作副本：工作区 `.worktrees/live-002-eng`，不与 ARC/003 共写。
- 独占：services/backend/（仅基础包/锁/配置/健康/worker预检/Alembic与基础测试）、infra/、scripts/checks/、.github/workflows/、docs/operations/backend-foundation.md、本卡、project-team/reports/LIVE-002/。不写STATUS/access/前端/契约。
- runtime：工作区 runtime/live-002；Compose live-fde-002；DB live002；端口 PG15432/MQ5673/管理15672/API8188（启动前探针无监听），127.0.0.1 绑定，不碰5432/6379/5188。
- 验收：Python3.11/uv固定锁；health/live200 与依赖失败ready503；独立PG/RabbitMQ真实连接；API/worker重启；worker ping；dispatcher明确仅check；Alembic基础真实PG启动（无业务修订）；Ruff/pytest；前端独立npm ci/build/hosting；结构/运行产物/敏感文件/rename两端与任务scope。
- 门禁：先 staged index 扫描，再独立 head Review；无远程不声称CI部署/PR创建。
- 未做：业务表/API、outbox、真实模型、部署发布；不以空迁移冒充业务验证。
- 回滚：revert本任务代码，仅关闭live-fde-002容器，保留runtime数据；不删除用户卷。
- 证据：reports/LIVE-002 与 docs/operations/backend-foundation.md。
- SHA/独立验收：见下；PM-01任务01a10b7c-30e0-7fa3-9545-0001d85a33b3业务范围核对通过。

- 独立Review：/root/qa_live002批准18e721f3c123b064104c90d94732374d6ed80063；main集成19fede3。PM已确认工程范围完成，接受明确未测限制。
