# 视频号上游取流及录制机制对照

2026-10-08 查询官方仓库 main，返回固定 SHA `07271abdb5707cf8074483a33c2519b457ccc669`，与安装参考版本相同；不需要盲目升级依赖。官方来源：[仓库](https://github.com/gtoxlili/wechat-finder-dlna)、[CLI](https://github.com/gtoxlili/wechat-finder-dlna/blob/07271abdb5707cf8074483a33c2519b457ccc669/wechat_finder_dlna/__main__.py)、[UPnP](https://github.com/gtoxlili/wechat-finder-dlna/blob/07271abdb5707cf8074483a33c2519b457ccc669/wechat_finder_dlna/upnp.py)。

| 环节 | 上游实际机制 | 本系统与本轮处理 |
|---|---|---|
| 发现 | 物理网卡私有LAN IPv4优先；SSDP组播及MediaRenderer描述 | 同一固定CLI，仅DLNA；任务按需启动 |
| 接收 | SOAP SetAVTransportURI，提取CurrentURI并html.unescape；首次URL设event，返回原地址，清理接收器 | 私有stdout管道，URL只在内存，不写Job/日志；保留原行为 |
| DLNA回调 | SUBSCRIBE回调/STOPPED事件维持投屏协议；不是媒体获取header | 未当作媒体Referer/Cookie来源；局域网接收器需可信LAN |
| 协议 | README展示http://pull-l1.wxlivecdn.com/...；CLI不强制或转换HTTPS | 漏接点是原URI与全局HTTPS-only冲突；增加受限HTTPS候选，不把HTTP响应等同不支持TLS |
| headers | _record未设置专用headers/Cookie/Referer；FFmpeg使用自身默认网络请求 | relay用通用User-Agent与identity编码，无Cookie；无证据需添加私密headers，不猜测或复制浏览器凭据 |
| HLS/重定向 | 地址直接进入FFmpeg，HLS子资源/重定向由FFmpeg处理 | 保持内存relay；统一覆盖初始、绝对/相对HLS URI及重定向的验证与候选适配 |
| CDN | 上游无域限制 | 继续受stream_domains及公网IP限制；仅wxlivecdn域边界可生成视频号HTTPS候选 |
| 输出 | ffmpeg -hide_banner -loglevel info -re -i URI -c copy，按可选-t、-y输出 | 继续已有受控FFmpeg：loopback输入、协议/格式白名单、指定音视频、视频copy/音频AAC、fragmented MP4、时长/空间保护；不为协议适配重写封装 |

本系统不直接使用上游录制路径，以保留网络与任务隔离、停止/取消、材料闭合与导入。候选升级不是复制上游已有功能，是兼容其原始URI与本系统HTTPS规则。

证据层次：失败任务已到recording阶段入口但未产媒体；错误在relay首次DNS/TLS前触发。公开示例主机证书/SNI/TLS1.3握手成功，不含用户签名或媒体请求。用户真实投屏URI没有持久化，无法补做原签名测试。后续新版手机重投才可验收实际CDN与签名；任何单元/合成测试不得代替真实录制结论。

边界：上游HTTPServer的可信局域网/无认证及SUBSCRIBE回调机制未在本轮重构，不能声称已支持不可信网络或公网接收。不存在自动断流续录、手机内容绕过或AirPlay加密音频接入。本轮不调用ASR/LLM。
