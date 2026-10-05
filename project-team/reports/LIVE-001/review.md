# LIVE-001 ARC 独立技术审查

- reviewer：ARC-01，技术统筹任务 01a0ff89-4e64-7242-a012-92850d916a87。
- 执行者：ENG-01 子任务 /root/eng_live001；不与审查者共用执行身份。
- base SHA：无，首次仓库基线例外；提交前绑定 staged tree。

## 搬迁清单审查
2026-10-05：已读 inventory.md 和 docs/operations/live-001-migration.json，批准列明的 20 项搬迁。
目标归档目录此前不存在；源码与资料保全，不改原 CPB，不覆盖客户资料。
核实 design/ui-prototype-20261003 为本工作区普通文件；docs 为 app/docs 符号链接，均保持。
确认端口 5188 PID 19287 的 cwd 为原 prototype；明确协调 ENG 停止/重启，不误停其他服务。
前端 tmp/pdfs 和历史 qa 属验收/参考产物，移入 runtime，不 stage；public/assets 必要生成素材保留。

## 迁移前浏览器基线
使用 Playwright CLI、独立 Edge 会话 live001。Chrome 不存在，已改用已安装 Edge，未安装额外浏览器。
浏览器逐路由访问并检查 main 与标题：/、/sessions、/sessions/s1、/reports、/weekly、/reviews、/library、/plans、/plans/plan1、/settings 全部 HTTP 200、标题匹配。
原有 favicon.ico 404 是迁移前已存在的非阻塞问题；不是业务异常。一次探针误用不存在的 p1 ID 导致等待失败，改用数据中实际 plan1 后全部通过。

## 提交门禁
待搬迁/构建/浏览器回归后核对 staged 文件与敏感信息，未完成前不批准提交。
