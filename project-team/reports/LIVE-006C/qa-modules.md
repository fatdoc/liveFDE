# LIVE-006C 模块集成审查

2026-10-06，独立QA /root/qa_live001，非本轮代码作者。

## Tencent
批准单模块提交 a3464b59e64faca4b6800380d98a839b25419fbf 集成。固定SHA静态审阅与18协议mock测试通过。审批限官方file TC3和realtime V2适配器；文件规范WAV<=5,000,000bytes，不含长文件自动切段/COS；没有真实云权限、计费或准确率验证。

## UI
批准 b01a267（含9c1bc15）模块集成。独立复审增量已对齐10次/$100，health中文提示保留原码，腾讯规范WAV5MB约156秒限制已明确；没有把原压缩文件大小当规范WAV大小。作者真实浏览器证据明确只覆盖登录/设置持久/冲突/健康，不冒称转写已验证。QA未重复执行作者浏览器操作，实际转写端到端仍待最终独立验收。

本地fallback但不授权云端的提交是否可用仍依赖ARC待提交的authorization修复。这些模块批准不构成006C整轮交付批准。

## QA资源
独占数据库127.0.0.1:15480/live006c_qa_stream_20261006，用于固定37f70b8 WS验收；没有操作主库或作者库。代码快照、运行脚本与日志位于runtime/live-006c/qa-stream。模型/真实云均未调用。

## WebSocket

37f70b804f62debbfb7690c414f169a13b535983 的3文件增量静态审阅完成；固定SHA在QA独立PG库运行18项真实数据库/鉴权WebSocket测试全部通过（46.14秒）。覆盖Origin/cookie/CSRF、revision、授权、local/cloud模拟完成、无Outbox、unknown/incomplete、不可retry、cancel/disconnect/idle/字节限。日志 qa-stream/tests.log。首次缺测试环境broker_url导致setup失败，补上不可连接的127.0.0.1:1占位配置后通过，未启动broker。

批准该单模块集成；组合前置门禁仍要求ARC注册路由，修正recover_expired不得将无原音stream重新queued/创建Outbox，并验证其测试。运行中失联与崩溃恢复是不同路径，本18项不能冒充共享崩溃恢复修复已验证。未测试真实麦克风/编码、实际云服务或LOCAL模型。

测试进程退出，保留QA独立库及合成产物作为证据；未停止共享PG容器，未修改作者/main代码。无P0/P1模块内阻塞。
