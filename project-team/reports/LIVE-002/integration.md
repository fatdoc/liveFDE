# 本轮集成验证

代码集成：LIVE-003 main 26aaf4a（批准源 b7d4efa）；LIVE-002 main 19fede3（批准源18e721f）。ARC于2026-10-05在app主checkout实际执行：

- uv locked sync 成功；pytest 3通过，保留1条Starlette httpx弃用警告；Ruff通过；目录门禁3测试通过、全index扫描0违规。
- uv run --project services/backend --with jsonschema==4.26.0 python docs/contracts/check_examples.py：17正常/15负例通过。
- 原生MQ模式runtime_smoke在集成版本完整退出0：健康200、worker pong、dispatcher preflight、API/worker重启、PG与MQ分别中断503/恢复200。运行日志与smoke-results.json留workspace/runtime/live-002。
- 运行结束停止自己的API/worker/原生MQ，PG及数据保留。8188不是常驻接口；Demo保留5188。

前端未改源码，本轮ENG在独立worktree的npm ci/build/4项hosting已通过；未新增浏览器业务回归或模型测试。业务契约仍为设计稿；无业务表、认证、真实分析或爬取交付。独立QA记录review.md；Compose MQ未验及远程CI未跑见follow-up.md。

PM-01（任务01a10b7c-30e0-7fa3-9545-0001d85a33b3）已核对独立review与集成代码无diff，接受工程范围交付；002/003均可标done。未要求PM重复扰动运行服务。
