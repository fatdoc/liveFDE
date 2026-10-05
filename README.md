# 直播复盘与资产工作台
Python + React + PostgreSQL，单客户独立交付。
导入录像 → 转写/画面证据 → 单场/周总结 → 人审话术 → 学习资产 → 下一场备播。

## 当前事实（2026-10-05）
React Demo 位于 frontend/web/，覆盖场次、报告、周总结、审核、资产、备播和设置；业务仍为演示状态。
本目录是唯一产品 Git 根；LIVE-001 本地基线与审查结果见 [任务状态](project-team/STATUS.md)。未配置远程仓库。
旧 CPB 副本已移到工作区 archives/cpb-reference-20261005，只读参考，不代表新业务后端已接通。
新后端目标 services/backend/，按 [开发计划](docs/05-delivery-plan.md) 后续实施，当前没有后端实现。

[文档入口](docs/README.md) · [员工与边界](docs/10-digital-team.md) · [目录搬迁清单](docs/operations/live-001-migration.json)

## 前端开发
在本目录执行 `npm --prefix frontend/web ci` 安装锁定依赖；开发预览、构建与 hosting 检查：

```sh
npm --prefix frontend/web run dev -- --host 127.0.0.1 --port 5188 --strictPort
npm run build
npm run test:sites
```

预览 http://127.0.0.1:5188/ 。构建产物与依赖不入 Git；历史原型截图/PDF 渲染保存在工作区 runtime/prototype-qa-20261005。
不要使用归档 CPB 启动指南启动新平台。抖音/视频号采集安排在 M5。
