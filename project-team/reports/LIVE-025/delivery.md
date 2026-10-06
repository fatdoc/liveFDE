# LIVE-025 工作区抖音接入设置

基线52bfde6；代码9e9c80eb553edf9b9ceb1d0b43fa64b5b7785cce；PR https://github.com/fatdoc/liveFDE/pull/16 。合并/本地部署在验收完成后单独记录。

## 改变

设置→平台接入→抖音支持管理员保存、更新、清除Cookie及一次有界检查。响应只返回状态和revision，SecretStr请求输入不出现在验证错误，workspace私密存储目录0700/文件0600，路径位于下载对象外，原子写/进程锁/版本竞争保护。它是OS权限保护明文，不是加密保险库。无数据库迁移或依赖变化。API与worker工作区流程显式传凭据(含空值)，禁env和上游示例回退；任务参数不含Cookie。

开始解析前取快照；更新/清除影响后续检查与尚未解析的排队任务；已运行任务继续旧快照直到结束。检查只调用一次parser，不启动Job/FFmpeg/ASR，不访问CDN；开播返回必须满足静态HTTPS/域策略，未开播只证明解析有效。拒绝访问不直接断言Cookie过期；空响应/网络/格式错误均保留准确原因。

原DLR主循环非h265优先FLV，旧桥仅取HLS优先record_url。现在先按FLV偏好排列，再仅选择明确返回且符合静态策略的候选；不改写scheme，不扩域，不放宽TLS、重定向或HLS资源检查。所有候选不满足时提前明确报错。原始上游仍固定add187f8，未动其目录。

## 验证与真实边界

作者隔离PG150通过(245s)，证据runtime/live-025/live025_suite_c92bcae654ab413d90b423f736abb33d；首次测试因缺fixture导入124通过/24 setup errors，已修复并完整重跑，保留初次证据，不隐藏失败。root桥选流最终34通过，工程42通过，前端build、hosting4、分类5通过；Edge8类合成API交互见frontend.md。第一次root前端build因临时node_modules链接位置写错未执行tsc，纠正链接后完成通过。

真实既有Cookie单次解析原授权房间返回live，前后run总数7不变，无录制。随后用户自行录制另一授权房间失败https_required：run87cac7e4-b945-434d-ba42-3071e3872378，job55adf80d-7482-44da-9934-304afd7531b1，failed/active=false，manifest/material为空。旧记录没有区分初始地址/重定向/HLS子资源失败阶段，不据错误码断言唯一根因。后续一次授权仅解析诊断返回的record_url/flv_url/m3u8_url全部HTTP、host pull-t3.douyincdn.com；未访问CDN、未录制，无原始URL/查询/Cookie留存。修复能准确选流和提前拒绝，但不证明该房间现在可录制。

独立非作者QA-02批准9e9c80e：原4f0ad9b完整选集150 tests/0 errors/failures/skips（266.791s），最终代码差异bridge34通过、FE语义5通过、额外跨spawn进程锁/clear竞争2通过。组合证据不是宣称对最终代码重复跑完全部150。报告runtime/live-025/qa-fixed-review.md；选集live025_suite_e24c790fece54f439a1829b551c1215f。CI与本地设置页仍待完成，不据当前记录宣称已部署；后续运行交接与最终CI/main SHA写runtime/live-025/closure.json。尚未真实完成抖音录制、视频号、跨用户生产部署或端到端出站隔离验收。评分/报告仍Demo，不将本轮接入设置冒充全平台交付。

## 回滚

保持既有数据库/媒体/失败记录；版本回滚保留runtime私密文件，不将其放入Git/交付包。旧版本仅理解进程env，回滚需运营者明确选择并安全配置，不自动把工作区秘密转全局。停服务前确认无活跃run/job/outbox，SIGTERM并确认退出；无法确认则停止交接。
