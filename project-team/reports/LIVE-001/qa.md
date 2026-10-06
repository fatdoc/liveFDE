# LIVE-001 实际验收

ARC 浏览器验收，独立于执行搬迁的 ENG。日期 2026-10-05。

## 已验证
- 迁移前后相同 10 路由：/、/sessions、/sessions/s1、/reports、/weekly、/reviews、/library、/plans、/plans/plan1、/settings，全部 HTTP 200 且标题正确。
- 各页面 img.complete/naturalWidth 检查通过，brand.png 和 presenter.png 正常加载。
- 审核页将示例教学说明改为迁移验收文字，批准后待审 8→7、已入库 5→6；学习库出现该资产。
- 该资产加入备播后进入 /plans/plan1，适配文字进入正文、增加已审核来源引用；原话未被覆盖。
- 报告总览编辑并保存，版本变为 v2/待人工复核；导出 Markdown 预览包含本次修订，示例边界仍显示。
- 备播页面截图已人工查看，版式和编辑区正常。截图/浏览器日志保存在工作区 runtime/live-001/output/playwright 及 .playwright-cli，不进产品 Git。
- ENG build 通过；hosting 4/4。独立 QA 又复核 hosting 4/4、41 文件哈希和17项归档数量/体积、锁一致性、staged 格式与敏感候选。
- main 初始提交 13665739fb29d8aa70a9e78d32bce3d58c81bd0f 的 tree 等于独立批准 tree e61ac5e761e0e8c5949f3a4f0fdc3e82e2cb0199。
- git worktree add --detach ../.worktrees/live-001-qa-probe HEAD 成功；新工作副本 clean、SHA 相同；git worktree remove 正常完成。当前仅 app 主工作树。
- 预览 http://127.0.0.1:5188/，PID 69984 cwd frontend/web；无原 prototype 服务依赖。

## 明确限制
- 本轮是结构与基线验收，不是后端、真实转写/分析、数据库持久化验收。Demo 刷新后恢复示例是既有行为。
- 本轮验证导出正文预览，没有声称操作系统下载落盘或打印 PDF 成功。
- 迁移前已存在 favicon.ico 404、Vite bundle 约772KB提醒；非本次迁移引入，留后续前端任务。
- 未创建远程/PR、未发布、未调用付费模型。原 CPB 与客户资料只读。

## 可追踪产物
目录映射和保全哈希：docs/operations/live-001-migration.json。
静态独立 Review：independent-review.md；工程命令与结果：implementation.md。
