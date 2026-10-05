# LIVE-001 搬迁前清单
状态：待 ARC 独立批准；未执行搬迁。
所有目标均在当前工作区；cpb-reference-20261005 尚不存在，存在则停止，禁止覆盖。

| 当前路径 | 目标 | 文件数 / bytes |
|---|---|---|
| `app/backend` | `archives/cpb-reference-20261005/backend` | 520 / 4636102 |
| `app/ai-scoring` | `archives/cpb-reference-20261005/ai-scoring` | 14698 / 108600533 |
| `app/frontend/admin` | `archives/cpb-reference-20261005/frontend/admin` | 40 / 309142 |
| `app/frontend/user` | `archives/cpb-reference-20261005/frontend/user` | 42451 / 436400751 |
| `app/frontend/teacher` | `archives/cpb-reference-20261005/frontend/teacher` | 76 / 953566 |
| `app/recording-bot` | `archives/cpb-reference-20261005/recording-bot` | 5 / 113966 |
| `app/signaling` | `archives/cpb-reference-20261005/signaling` | 6 / 54538 |
| `app/sql` | `archives/cpb-reference-20261005/sql` | 7 / 56007 |
| `app/livekit.yaml` | `archives/cpb-reference-20261005/livekit.yaml` | 1 / 489 |
| `app/livekit-egress.yaml` | `archives/cpb-reference-20261005/livekit-egress.yaml` | 1 / 201 |
| `app/livekit-proxy.js` | `archives/cpb-reference-20261005/livekit-proxy.js` | 1 / 2797 |
| `app/package.json` | `archives/cpb-reference-20261005/package.json` | 1 / 200 |
| `app/scripts` | `archives/cpb-reference-20261005/scripts` | 1 / 30 |
| `app/UI资料 2` | `archives/cpb-reference-20261005/UI资料 2` | 0 / 0 |
| `app/source-migration-core` | `archives/cpb-reference-20261005/source-migration-core` | 0 / 0 |
| `app/javac.20260814_120403.args` | `archives/cpb-reference-20261005/javac.20260814_120403.args` | 1 / 71 |
| `app/项目启动指南.md` | `archives/cpb-reference-20261005/项目启动指南.md` | 1 / 10712 |
| `app/frontend/prototype` | `app/frontend/web` | — / — |
| `app/frontend/web/qa` | `runtime/prototype-qa-20261005/qa` | — / — |
| `app/frontend/web/tmp` | `runtime/prototype-qa-20261005/tmp` | — / — |

保留：app/.git、.github、AGENTS.md、PRODUCT.md、README.md、TASK.md、docs、project-team；重写根 .gitignore/.dockerignore/package.json 入口。旧 ignore 原文也保全到归档根。

## 进程与链接
当前 npm PID 19269、Vite PID 19287、esbuild PID 19288，cwd 为 app/frontend/prototype；Vite 监听 127.0.0.1:5188。搬迁前显式停止本项目进程，迁后从 web 重启同端口。
Python 51101 的 8897 服务 cwd 属于工作区外赛制项目，不触碰；本机 PostgreSQL 5432/Redis 6379 未归属本项目，不使用。
app 排除依赖/.git 后无软链接；外层 docs → app/docs 不变。外层 design 链接须由 ARC 核对来源边界。
未发现 app 内 .env/.pem/.key 私有配置（排除依赖/.git，只检查路径）。旧 LiveKit YAML 等配置整体仅留本地归档，不读出配置值。

## Demo 保全与验收
迁移前 41 个源码/静态资产/锁/hosting 文件 SHA256 已写 docs/operations/live-001-migration.json；迁后逐一核对，预期仅 README 路径文档有明确更新。
node_modules/dist 随目录移动但忽略入库；qa/tmp 原样移到 runtime/prototype-qa-20261005，保留历史证据并修正文档链接。
执行 npm run build、npm run test:sites；确认 dist/client/index.html、dist/server/index.js、dist/.openai/hosting.json。ARC 独立浏览器检查全部已存在路由、静态资源、报告/审核/备播交互。
不 stage、不提交：交给 ARC 审查确定后的精确清单。搬迁失败按 JSON 逆序恢复，目标冲突立即停止。
