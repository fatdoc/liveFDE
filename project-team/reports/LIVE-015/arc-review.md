# LIVE-015～017 第一轮技术审查

状态：需要修复，未批准、未合并。2026-10-06。

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
