# 目录契约
ARC 负责结构，ENG 执行搬迁，QA 检查。新顶级目录必须先登记；现有模块职责内增加普通文件无需逐个询问用户。

## 当前与目标
Git 根 app/；外层 docs 是 app/docs 符号链接。LIVE-001 已将前端迁到 frontend/web、旧 CPB 移到 archives/cpb-reference-20261005。下图中 services/backend、infra 等后端目录仍为后续目标，不提前建空壳；实际清单见 operations/live-001-migration.json。
```text
直播体系FDE/                        工作区
├── app/                           唯一产品 Git 根
│   ├── AGENTS.md / README.md / PRODUCT.md / TASK.md
│   ├── frontend/web/              现有 prototype 迁名，不复制第二套
│   ├── services/backend/
│   │   ├── pyproject.toml / uv.lock
│   │   ├── src/live_review/
│   │   │   ├── main.py
│   │   │   ├── core/              配置、DB、认证基础、日志
│   │   │   ├── modules/           identity、streamers、sessions、materials
│   │   │   │                     jobs、analysis、reports、assets、preparation
│   │   │   ├── integrations/      storage、media、asr、vision、llm、capture
│   │   │   ├── prompts/           版本化提示词
│   │   │   └── workers/           Celery、dispatcher、任务薄封装
│   │   ├── migrations/versions/   唯一 Alembic 位置
│   │   └── tests/                 unit、integration、fixtures
│   ├── infra/                     Compose、Dockerfile、代理、env 示例
│   ├── scripts/                   dev、checks、release 按需
│   ├── docs/                      规范、ADR、契约、操作指南
│   ├── project-team/              任务、员工、权限、验收
│   └── .github/                   PR 模板、后续 CI
├── archives/                      旧模板/CPB 私有本地参考
├── .worktrees/                    后续任务工作副本，始终在本工作区内
├── runtime/                       项目媒体/日志/本地运行数据，不入产品 Git
├── design/                        现有 UI 原图
├── 第一次需求拆解/                   原始资料，只读
└── docs → app/docs
```

## 搬迁方案
| 当前 app 内路径 | 处理 |
|---|---|
| frontend/prototype | → frontend/web，保留代码/锁/hosting，验证构建/路由/资源 |
| backend、ai-scoring | → 工作区 archives 的 cpb-reference 目录，只读参考 |
| frontend/admin、user、teacher 等旧端 | 核对后归档，不得误动 prototype |
| recording-bot、signaling、sql、LiveKit 配置、旧根 package.json/scripts | 清点确认 CPB 归属后归档，新部署文件归 infra |
| docs、project-team | 留在仓库，统一规则 |
| source-migration-core、UI资料 2、编译参数等 | 核对内容/链接，整理任务登记，不作为业务目录 |

归档目的路径由 LIVE-001 清单固定；存在则不覆盖，先保全。私有配置留本地，不进 Git/交付包。
先检查运行进程 cwd，避免破坏已有预览；迁移单独提交，不混业务重写。原 CPB 和客户资料不改动。
不为目标图批量创建空壳目录，首个实现任务出现时再建。

## 模块和依赖
模块按需要有 router.py/schemas.py/models.py/service.py/repository.py，简单 CRUD 不为层数建空 repository。
路由→service→repository/adapter；workers→同一 service。provider 不直接改业务表/审核状态；不跨模块直接写表。
禁止全局巨型 models.py/crud.py、万能 utils/common/misc；至少两个真实且语义一致的消费者才提取共享代码。
Python snake_case，React PascalCase；源码英文稳定业务名。new/final2/backup 不保存替代代码，版本交给 Git。
约 300 行触发职责检查，500 行需说明或拆分；不是机械按行数拆。模块多职责时 README 说明入口/归属/测试。

## 特殊文件位置
OpenAPI 快照 docs/contracts/openapi.json；生成客户端 frontend/web/src/api/generated/，禁止手改。
正式分析 schema 在 modules/analysis，prompt 文本在 prompts，不能各维护一份正式 schema。
小型合成 fixtures 可入库；客户媒体、权重、缓存、DB、日志放受控运行卷，不放 src/public/docs。
验收记录 project-team/reports/LIVE-xxx/，大媒体使用受控引用。

## 结构门禁
LIVE-002 实现顶级目录白名单、运行产物/未知路径检查、rename 两端 owner 校验。
存量旧目录是临时例外，注明 owner/解除任务；不允许继续在旧目录追加新系统代码。
自动检查只管可机械判断部分，不能代替职责 Review。目前尚未实现自动 CI。

用户明确所有项目模块均留在本工作区。worktree 统一使用工作区 .worktrees/<task-id>-<role>/，不用工作区外的默认路径；首次提交后再按任务创建。全局包缓存/Codex 元数据不要求搬迁。
