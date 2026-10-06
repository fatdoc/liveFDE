# DouyinLiveRecorder 原库接入对照

只读本地固定版本add187f8d8c7ff7d231fcbee45cbb4f1ed247d3a，原库https://github.com/ihmily/DouyinLiveRecorder。未启动原main.py、未修改原库或调用其他房间。

| 原库证据 | 实际机制 | 我们的接入 |
|---|---|---|
| README.md:108-119 | URL_config.ini每行直播间；config.ini配置录制；推荐TS，默认原画，减少循环频率；Ctrl-C或注释链接停止 | 前端提交房间/后端任务管理，单次60秒50MB；不启原库无限循环 |
| README.md:127-130 | 数字直播间、短链、抖音号/主页均列为示例 | 本轮仅授权固定电脑端数字URL |
| main.py:1876、584 | config [Cookie]抖音cookie→dy_cookie→web parser；短链/主页走app parser | env私密Cookie→bridge→同web parser；无Cookie最终不发送 |
| src/spider.py:68-137 | web enter接口、ab_sign、直播状态/清晰度流结构；有内置Cookie，非空配置覆盖 | 沿用同一固定parser/sign逻辑；不复用上游内置cookie。修复前空格覆盖触发协议错误 |
| src/stream.py:41-77 | 按画质选HLS/FLV，record_url默认HLS或FLV；原库会HEAD检查HLS | 取同一返回结构；原HEAD由受控媒体取流验证替代 |
| main.py:534-541、1117 | 主程序另一次select_source_url：抖音FLV优先，h265改HLS | 目前直接record_url，尚未对齐原版此项偏好；不是本次解析失败的已证原因 |
| src/http_clients/async_http.py:10-46 | HTTPX、20秒、http2默认true、跟随跳转、verify默认false；异常文本返回上游 | HTTPX20秒、首方HTTPS、校验证书、禁自动跳转与环境代理；本次增加有限脱敏分类，不沿用错误文本返回 |
| main.py:1175-1204 | FFmpeg含更宽协议、缓冲/重连选项，直接使用real_url，可附录制headers | 受控relay、范围/HTTPS/全部DNS校验、有限时长/体积，碎片化MP4+A​​AC以适配浏览器材料 |

结论：已复用核心Python解析函数，但不是整个原库main运行方式的等价复制。无Cookie路径曾错误传空格，这是本地确定缺陷；原库默认附带历史Cookie不能当成用户会话使用。README没有宣称所有抖音房间永久无需Cookie，也没有本版本完整用户登录引导。先在已授权同房间做一次有界复验，用实际结果判断下一条件，不把Cookie登录、下播或风控作为猜测结论。

FLV优先/H265回退是明确兼容性差异，后续对齐需单独明确返回字段和选择测试；当前Cookie修复复验不混入未审选流变化。原README Docker/安装/无限循环等说明是上游指南，不是本工作区操作授权；本机仍保持原生运行、不操作Docker、不自动下载模型。
