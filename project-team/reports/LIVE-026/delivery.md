# LIVE-026 HTTPS协议适配与一次真实录制

基线8a76d7b；代码79586deaedf51170313c41174c8c2ac74d88d1d5；PR17。ARC实现，QA-02非作者固定SHA批准，审查证据runtime/live-026/qa-fixed-review.md。

补齐固定DLR main.py1150–1151协议层：优先原始合格HTTPS，再仅对同时命中配置白名单与douyincdn.com边界的HTTP默认端口生成HTTPS候选。路径/签名查询原字节保留，显式80去掉以用443；不改任意字符串/域/端口，不发送Cookie到CDN，不自动回退HTTP。没有依赖/迁移/UI变化。TLS证书、逐跳域/IP、HLS子资源、停止与原时限均由原relay执行，未放松策略。

作者53解析测试；独立111 tests（bridge/providers/resolution/recording）零失败/错误/跳过，23.701s；工程42、scope与按backend pyproject执行的Ruff通过。没有用模拟结果代替下述真实录制。

在确认无活跃run/job/outbox后SIGTERM并确认旧API59405/executor59414退出；部署已审79586de至API65834/executor65849，UI59415保留。原workspace凭据保留，无全局Cookie注入，未改HTTPS/域/60秒50MB策略。按用户本轮明确授权，对最近一次失败记录的房间仅提交一次采集，没有独立CDN旁路探针或自动重试。

真实run3407c23d-cc55-459b-8198-0950f5e12b6d：queued→probing→recording→recorded→imported，job succeeded/error null。material41507f74-c477-4744-be5a-558ff0496480，媒体20,534,651字节（约19.6MiB），60.067秒，H264 1080x1920视频+AAC音频，closed=true。end_reason=duration_limit、complete=false正确表示达到60秒试录预算的片段，不宣称整场完整；容器时长含音视频包尾差。原始所有失败保留，无ASR调用。

前端真实Edge验收：场次材料出现真实录像；HTMLVideo duration60.067、1080x1920，静音播放后currentTime1.449113、readyState4、error=null。只验证浏览器播放和音轨存在，没有据静音播放断言听感或识别质量。证据runtime/live-026/record-result.json、real-playback.png；完整私有媒体仅在runtime，不入Git。

当前结论：此授权房间的一次HTTPS采集→导入→前端播放闭环通过；不泛化所有房间、长期稳定录制、视频号或ASR。最终CI/合并SHA见runtime/live-026/closure.json。回滚可切回8a76d7b并保留私密配置与媒体，旧版本会继续拒绝这类HTTP来源；切换前必须确认空闲并drain。
