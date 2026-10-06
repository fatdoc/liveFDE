# GitHub CI

远端：<https://github.com/fatdoc/liveFDE>。工作流 `.github/workflows/checks.yml` 在 push 和 pull_request 时运行，权限为 contents:read。CI 通过不等于部署、真实平台采集或真实模型验收；分支保护需另行配置。

## 执行内容

1. 从事件获取分支/基线，检查登记任务的路径权限、仓库结构和敏感文件禁入规则。
2. 运行 scripts/checks 的工程安全单测；锁定 Python 3.11 和 uv 0.9.26，按 uv.lock 安装。
3. 后端 Ruff、Node 22 下前端依赖锁安装、类型检查/构建及站点测试。
4. 安装 FFmpeg；在 runner 的仓库同级 runtime/live-002 生成本次随机凭据，文件权限 0600。
5. 通过项目 Compose 启动独立 PostgreSQL/RabbitMQ，执行 Alembic、API 健康检查、worker ping、重启和依赖故障恢复。
6. 运行整个后端 pytest 集合，要求零跳过；清理本次 Compose 服务；验证契约样例。

GitHub 托管 runner 之间互相隔离。本机不要为了模拟 CI 设置 GITHUB_ACTIONS=true 并对历史数据库运行集成套件：本机应使用已登记的隔离验收环境。CI 不读取或上传开发机 .env、模型缓存和客户媒体，不提供云模型密钥。

## 本地快速验证

在产品仓库或工作区内的独立 worktree 执行：

```sh
python3 -m unittest discover -s scripts/checks -p 'test_*.py'
uv sync --project services/backend --locked
uv run --project services/backend ruff check --config services/backend/pyproject.toml services/backend scripts/checks
python3 scripts/checks/repository.py --task LIVE-019 --base 0cbd317f041be899ec49eb2faed82ea036619591
```

最后一项是本轮示例；新任务必须替换登记的任务号和真实基线。

LIVE-006/006B 原始环境脚本保留本机 checkout、凭据权限、目标数据库、Docker endpoint 等资源限制。它们的单元测试在测试生命周期内模拟已登记 ROOT，以便 Linux/worktree 能测试后续拒绝规则；每次测试完成后自动恢复，错误 checkout 的拒绝测试仍运行。不要删除安全断言或改生产路径白名单来让 CI 通过。

## 排查

在 PR Checks 中打开失败步骤，先看首个失败。环境初始化成功后才会执行 Compose 清理；初始化之前失败时清理会跳过，避免缺失 private.env 掩盖首个错误。正常清理失败仍使工作流失败。

依赖安装、Docker 拉取、测试、迁移和恢复都必须成功；不使用 continue-on-error 或跳过集成测试作为适配方案。若后端集成报告有 skipped，脚本会拒绝通过。日志不要打印凭据、完整 DSN、用户转写或原始音视频。

历史开发分支可能仍带旧版工作流；本轮验收绑定修复 PR 的最终提交及合并后的 main，不表示所有历史分支都会变绿。
