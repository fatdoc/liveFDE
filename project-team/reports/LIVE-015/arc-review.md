# LIVE-015～017 第一轮技术审查

首轮历史状态：需要修复，未批准、未合并。2026-10-06。最新有限批准见文末。

审查基线：CAP `154e2cd` → `a1702c0a7bbcc93699c79fdd9a09d45351fb57ac`。ARC为非实现作者，任务 `01a0ff89-4e64-7242-a012-92850d916a87`；独立QA为 `/root/qa_live001`。主仓库仍为 `209fc612c1fd1f02b09208e53d7981ee201afe56`。

## 已取得的证据

- QA独立数据库 `live015_qa_0be897c1e18d4de09e8a00970799696b`，PG15490；JUnit位于工作区 `runtime/live-015/qa/live015_qa_0be897c1e18d4de09e8a00970799696b/pytest.xml`。ARC实际解析：22项，21通过、1失败、0跳过。不能用作者22通过替代该结果。
- 正常HLS音视频对照结果 `runtime/live-015/qa/hls-av/result.json`：直连退出码0，经relay退出码183，FFmpeg拒绝被改名为 `.media` 的分片。此为本地合成媒体，不是真实平台录制。
- QA消息报告播放列表部分URI属性可绕过受控转发，为P1阻断。已交作者修复，未经新版本复核不得恢复真实直播测试。
- ARC源码核对：执行入口缺少与既有media worker一致的actor有效性及workspace复验；共享导入入口只捕获ApiError，CaptureError路径未持久保存具体诊断。已交作者补行为和回归。
- 失败项 `test_interruption_preserves_closed_partial[duration-duration_limit]` 在1秒墙钟限额内未取得媒体文件，抛出duration_limit。需检查替代进程启动同步，不能删除时限保护或以挑选成功重跑掩盖失败。

## 审查边界

QA代理后续分析被平台自动安全检查以possible cybersecurity risk中止；随后普通结果整理请求亦未完成。没有最终独立批准，不将其失败消息当作审查结论，也不继续被拦截的探针。上述JUnit与正常HLS对照由ARC直接核对实物；安全问题为QA已送达消息，复核状态仍未完成。

CAP负责修复并给新SHA；新增代码需重新审查。PM已收到暂缓真实直播/手机操作通知。真实平台、真实手机和本轮真实ASR调用均没有通过证据。LIVE-004及LIVE-006C原验收不受本轮未合并代码影响。

## 固定修复版本的独立技术验收

非实现作者ARC审查 `e78014b5f84461b3775d1ad246201445c5a6376c`，作者副本干净并冻结。独立执行完整后端回归352项，0错误/失败/跳过；证据 `runtime/live-015/evidence/live015_suite_a912d8a318ca42dfb7d758d4de6ea90f/pytest.xml`。该版本包含最终API及worker导入状态保留修复。Broker集成测试沿用验收脚本明确排除，本轮未重新验证生产消息队列部署。

独立静态复核严格HLS标签/属性解析、支持URI统一受控重写与安全分片后缀；纯解析拒绝断言及正常/AES-128合成HLS录制回归通过。执行期actor、job/run/workspace、场次归属复验覆盖worker和API导入；共同retained_state保持已导入事实。manifest有严格结构、时间与大小限制；导入错误保留具体诊断。

ARC另直接读取并完整解码作者最终专项的两份HLS实物：H.264视频+AAC音频，2.220136秒，manifest时长2220ms，SHA256一致，完整解码退出0。两者均closed、source_eof_unconfirmed，不冒称平台已确认结束或真实直播。文件位于 `runtime/live-015/evidence/live015_suite_f7765c45af814ec490788b81a3239ea7/tmp/test_actual_hls_ts_relay_recor{0,1}/recorded-hls/`。

Ruff与scope检查通过、diff无空白错误；主仓库旧36项工程检查及作者副本新环境/scope8项检查均由ARC独立执行通过。Alembic唯一head为0006_capture，check无待生成变更。旧迁移和产品依赖锁未修改。

默认关闭门禁由ARC独立执行入口断言：无capture配置时enabled=False，API start/probe及worker/operator共用run_stage返回capture_not_configured；helper收到模拟422拒绝后Popen未被调用。此为入口函数/命令行隔离断言，不冒称完整真实HTTP或平台联调。stop/status保留用于已有任务收尾，不启动采集。

作者另一次全套 `live015_suite_53695a0ce5584bec9af370bcdcfebd5a` 为350通过/2失败/0跳过，因运行期间修改模块造成旧ingestion缓存无法导入新增retained_state。失败保留，不作为固定版本证据。最终独立352项是在冻结e78014b之后开始，期间无代码修改。

结论：批准上述固定SHA作**默认关闭的基础代码技术集成**。已知修复通过静态审查与上述功能回归；原被拦截的网络探针未重跑，端到端出站隔离安全复核仍未完成，不批准真实来源启用。PM任务01a10b7c-30e0-7fa3-9545-0001d85a33b3明确接受这一有限范围，要求015～017保持待产品验收，不能标done，不启动8197/DLNA。真实平台、手机和本轮真实ASR均未验。集成代码SHA与主仓库后续验证另记integration.md。
