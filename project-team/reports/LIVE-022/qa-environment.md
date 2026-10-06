# LIVE-022 原生环境脚本独立 Review

审阅者：/root/qa_live002，本轮未参与三份脚本作者工作。
固定 head：76ce3894771542b3a5c99e04bf4dcc6def54dbfc；parent：98fb4b9。
范围：scripts/checks/live020_environment.py、live020_acceptance.py、test_live020_environment.py。源码无修改，工作树核对固定提交一致。

结论：批准这三份环境/验收脚本的普通代码与功能范围；不代表CAP、FE、真实平台或整体LIVE-022交付通过。

独立验证：
- 环境单元测试3/3：固定15500/live020目的地、重复key与旧15480拒绝、权限/超限/FIFO/symlink拒绝；清除继承LIVE_TEST_DATABASE_URL/后台runner，固定开发origin5199，明确cookie例外。
- 自建离线mock harness验证acceptance七种结果：正常2 tests exit0；zero tests、skipped、errors、failures、missing JUnit均exit1；pytest非零3保留exit3。
- harness同时核对suite数据库随机命名、LIVE_TEST_DATABASE_URL指向该新库、测试origin覆盖为5188。DB连接与pytest执行全部mock，未访问数据库、网络、模型或启动子服务。
- 代码审查确认配置读取无回显私有值；环境URL严格绑定127.0.0.1:15500/live020角色；建新suite库不清理旧数据库，证据写入runtime/live-020/evidence随机运行目录。

说明及边界：
- 初读未提交草稿时发现测试origin5199与5188 fixture冲突；固定76ce389已包含5188测试覆盖，故该问题已消除，不作为本提交finding。
- 默认selected包含test_capture_executor.py，当前环境脚本提交尚未包含该CAP文件；root明确登记为CAP集成依赖，最终合入后才执行默认验收。脚本不会将missing tests误报通过。
- --all明确排除test_jobs_broker.py，不能表述为RabbitMQ集成验收。timeout或畸形JUnit会异常退出，并不误报成功；这些异常的证据完善可后续优化，不阻塞本轮。
- 未触碰15480/15490、未读取真实private.env、未运行真实库套件或之前被自动安全检查中止的网络探针；没有换工具重试任何被拦截操作。
- 本次仅离线mock/普通文件单元测试，不作安全专项验收结论。

证据：同目录check_acceptance.py为独立mock harness；已运行结果pass/zero/skip/error/failure/exit/missing全通过。后续实现改变相关脚本需重新核验。
