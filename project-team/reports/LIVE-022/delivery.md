# 本机采集界面联调交付

截至2026-10-06。CAP PR11集成main4dcab61；FE PR12集成mainf0a6ee6。环境/契约/独立报告由LIVE-022另走PR。作者、固定SHA和范围见arc-review.md与三份QA报告。

可查看 http://127.0.0.1:5199/sessions ，沿用原React。新管理员登录信息仅在工作区runtime/live-020/browser-account.json（0600）；实际浏览器验收会话已登录。API8199、PostgreSQL15500、存储runtime/live-020均隔离；旧5196/8196/15480和015资源不动。本机不使用Docker。

通过：
- 真实浏览器登录、创建主播/场次、列表/详情恢复；API Cookie/CSRF与PG持久数据。
- 原生capture执行器仅消费capture_v1、health/列表/停止；CAP作者361全套与48最终专项，QA独立集成361通过、0失败/跳过。MQ用例明确排除于本地--all，PR完整CI另含PG/MQ。
- 合成画面+既有公开语音样例MP4上传、关联、下载hash一致；实际Edge播放8秒、640×360、readyState4/error=null；浏览器下载hash一致。
- 空stream_domains/无Douyin配置下，真实视频号DLNA接收器页面启动→waiting_for_cast→停止→stopped，8200监听与进程确实启动后退出。没有手机/直播画面。
- 已入库材料经页面手动提交一次新本地转写，job68c074e8-e360-43ad-9c55-89498c6739f8 succeeded/revision5，complete=true、synthetic=false，Fun-ASR-Nano本地耗时94664ms；页面显示文本，handler正常停止。无新上传、allow_network=false、无云调用/下载模型。不由单样本推导准确率。

必须保留的失败与未验：
- 首次job3a7e154f-2d1a-4157-a9b0-455900ead472失败execution_stop_unconfirmed，can_retry=false。原记录不改、不重放；22:13:37对请求:1收到明确停止ACK后，才授权上述单次串行新验收。首次中断原因仍未定位；冷加载与并行资源压力只是未证实假设，需要后续诊断日志改进与重复性验证。
- 真实抖音/视频号抓取、手机投屏、真实来源到ASR全链、完整出站隔离仍未验；不开放真实试录。此前被自动安全检查中止的探针未重跑或换工具规避。
- 仓库默认关闭；本机receiver测试后恢复disabled，capture executor退出、8200关闭。API/前端/ASR服务保留供查看，ASR空闲模型卸载机制仍在。
- 报告、评分、资产审核、学习库、备播后端仍未实现，Demo明确分开。评分标准待配置，无假分数或假报告。

主要运行证据（不入Git）：runtime/live-020/evidence/browser-material.json、first-asr.json、serial-browser-asr.json/png；独立361套目录live020_suite_c52f299d628647ad87bc88305bf00543；浏览器快照与视频下载在runtime/live-020/output/playwright。代码/文档验收与真实平台验收分开。

远程：PR10登记及PR11/12的pull_request事件完整CI通过。初次CAP/FE分支push因登记cherry-pick与全零before导致历史范围检查失败，后续PR使用已登记main基线通过；不修改scope掩盖旧失败。PR11另一个push事件曾停在外部apt-get安装阶段，不能把PR事件通过描述为该重复事件完成。main与022最终CI状态以真实GitHub运行记录为准。
