# LIVE-006B 逐文件变更清单

相对基线 `74df3b1fed59079abcb3f8c8b5cebc47b7e68deb`，A=新增，M=修改。正文按职责分组，源码与验收报告分列；本清单含最终纯文档收尾，精确集成SHA和批准树见final-review.md。没有删除产品代码文件。

## 配置与使用说明

| 类型 | 仓库相对路径 |
|---|---|
| A | `.env.example` |
| M | `.gitignore` |
| A | `config/environments/development.yaml` |
| A | `config/environments/production.yaml` |
| A | `config/environments/staging.yaml` |
| A | `config/environments/test.yaml` |
| A | `config/local.example.yaml` |
| A | `config/models.yaml` |
| A | `config/profiles.example.yaml` |
| M | `docs/04-directory-contract.md` |
| A | `docs/ai/configuration-refactor.md` |
| M | `docs/ai/live006-acceptance.md` |
| M | `docs/ai/media-jobs.md` |
| A | `docs/ai/model-registry.md` |
| M | `docs/ai/provider-configuration.md` |

## 后端源码与测试

| 类型 | 仓库相对路径 |
|---|---|
| A | `services/backend/src/live_review/core/model_config/__init__.py` |
| A | `services/backend/src/live_review/core/model_config/models.py` |
| A | `services/backend/src/live_review/core/model_config/safe_io.py` |
| A | `services/backend/src/live_review/core/model_registry.py` |
| M | `services/backend/src/live_review/integrations/asr/__init__.py` |
| A | `services/backend/src/live_review/integrations/asr/factory.py` |
| A | `services/backend/src/live_review/workers/media_configuration.py` |
| M | `services/backend/src/live_review/workers/media_jobs.py` |
| M | `services/backend/src/live_review/workers/media_operator.py` |
| M | `services/backend/tests/test_media_jobs.py` |
| A | `services/backend/tests/test_media_registry_jobs.py` |
| A | `services/backend/tests/test_model_config.py` |
| A | `services/backend/tests/test_model_registry.py` |

## 工程验收入口

| 类型 | 仓库相对路径 |
|---|---|
| A | `infra/compose.live006b.yml` |
| A | `scripts/checks/live006b_acceptance.py` |
| A | `scripts/checks/live006b_environment.py` |
| M | `scripts/checks/repository.py` |
| A | `scripts/checks/test_live006b_environment.py` |
| M | `scripts/checks/test_repository.py` |

## 任务与审查记录

| 类型 | 仓库相对路径 |
|---|---|
| M | `project-team/STATUS.md` |
| M | `project-team/access/RESOURCE-LOCKS.md` |
| A | `project-team/reports/LIVE-006B/arc-review.md` |
| A | `project-team/reports/LIVE-006B/audit-design.md` |
| A | `project-team/reports/LIVE-006B/config-review.md` |
| A | `project-team/reports/LIVE-006B/config.md` |
| A | `project-team/reports/LIVE-006B/engineering-review.md` |
| A | `project-team/reports/LIVE-006B/file-manifest.md` |
| A | `project-team/reports/LIVE-006B/jobs-review.md` |
| A | `project-team/reports/LIVE-006B/jobs.md` |
| A | `project-team/tasks/LIVE-006B.md` |
| A | `project-team/reports/LIVE-006B/integration.md` |
| A | `project-team/reports/LIVE-006B/final-review.md` |
