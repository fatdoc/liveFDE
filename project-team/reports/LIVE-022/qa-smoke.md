# LIVE-022 合成材料 smoke 独立 Review

固定SHA：78aececd012a782eaa6c4bfa5d66180091d23c23。
审阅者：/root/qa_live002；未参与这两份文件作者工作。
范围：scripts/checks/live020_smoke.py、docs/operations/live020.md；工作文件与固定SHA一致。
结论：批准此范围的普通代码/功能与证据表述；无阻塞问题。不代表直播平台采集或整体安全专项验收。

检查：
- 写入前调用已审environment绑定LIVE020独立目标；API固定127.0.0.1:8199，Origin5199；不引用旧15480/15490数据库。
- 输入限制runtime/live-020/fixtures下解析后的MP4、0<size≤10MB；session UUID经真实API鉴权读取并要求“LIVE-020 合成”标题前缀。新httpx会话登录，不带其他浏览器cookie。
- 上传登记带内容hash和幂等key；pending才发送content；finalize后关联primary；最终读取content并比对SHA256，失败不写成功证据。
- 证据明确verified为真实API上传/关联/下载hash，platform_capture=false、asr_submitted=false；没有调用采集或ASR端点。
- docs区分本机开发与客户部署、合成链路与真实抖音/视频号、默认executor文件集成依赖、MQ排除；初始禁用策略/模型为初始状态说明，不冒称当前后续人工配置未变化。

证据核对：只读browser-material.json，session97cb39a5-91a9-4d3b-862f-9f701673bb74、materiala9d5271b-001b-4d1a-8de8-6f0148d84581。fixture synthetic-av.mp4为614022 bytes，独立离线SHA256与记录86d8e5d9199333c5cf90dcfdc3568254a669f0048fd0cb693eeab405d734843e一致；两项false声明一致。

未重跑HTTP写入、未新建数据、未运行网络探针。API执行成功来自作者既有证据，本审查未冒称独立执行过API闭环；独立执行内容仅文件hash核对。
