# LIVE-021 FE 实施交接

作者 FE-01 子代理 /root/eng_live001，工作副本 .worktrees/LIVE-021-frontend，分支 feat/LIVE-021-frontend；业务 base a680ff75e9509a2f879bee0106695cb49d59bd18，登记变更 cherry-pick 为 149b14b。此记录不是独立批准。

## 交付范围
- /sessions：复用管理员认证，真实场次分页、主播选择/新建及新场次。
- /sessions/:id：真实采集与材料；旧示例链接统一转 /demo/sessions/:id，真实详情无预设报告与评分。
- CapturePanel：enabled/execution/dependencies门禁，抖音PC数字URL与视频号phone_cast/设备指引；服务端列表恢复最近20次采集；停止待确认与录后自动导入分别显示。
- 采集创建请求的幂等key和固定source存sessionStorage；未知结果重试同一key，不自动重发；活动状态禁新开。退出或切换场次清除轮询。
- 已入库材料直接绑定播放器/下载链接；手动本地ASR以material_id提交、allow_network=false，无重复上传、无云端授权；任务ID本标签页恢复，未知请求锁住重复提交。
- Vite新增 LIVE_API_PROXY_TARGET 环境覆盖，默认8196保留；本轮5199显式指向8199。站点部署/依赖锁未改。

## 验证
2026-10-06：npm ci；npm run build（TypeScript+Vite+Sites产物）通过；npm run test:sites 4/4通过。

使用 playwright 技能、独立 Edge session live021 在真实浏览器执行 tests/capture-browser-contract.js，API由测试路由合成：
1. 服务禁用时开始按钮disabled。
2. 第一次POST模拟网络未知，第二次人工重试同一幂等key。
3. 刷新恢复服务器run，未额外创建。
4. stop返回仍running时显示等待确认，不显示已停止。
5. recorded+活动任务显示导入中，再到material_id显示已导入。
6. 材料ASR仅1次提交，material_id既有、allow_network=false，未请求上传。
7. 视频号显示服务端设备名称与phone_cast操作指引。
8. 退出登录卸载采集界面回到登录表单。
返回 passed 共8项，capturePosts=2（同key，含一次未知），asrPosts=1。

初次断言因逐字内容与时间标记同段，exact文本匹配失败；实际浏览器已显示转写。修正为包含文本定位后通过，未用失败冒充通过。

## 未验与限制
真实后端认证、真实创建与媒体解码/Range下载交ARC独立集成验收。测试视频内容为空，仅验证播放器引用正确API，不声称实际可播放。未连接真实抖音直播间、未手机视频号投屏、未触发真实模型或付费服务。首次主播列表最多100项，材料最多100项、采集历史最近20项，本轮试录范围内；历史分页后续可扩展。ASR unknown未提供任务搜索接口，保留防重提示并可输入已核查的任务ID。已有bundle约806KB warning未做无关拆包。

## 资源与复测
UI http://127.0.0.1:5199，启动命令：LIVE_API_PROXY_TARGET=http://127.0.0.1:8199 npm --prefix frontend/web run dev -- --host 127.0.0.1 --port 5199 --strictPort。
浏览器契约测试需该UI运行，使用 playwright-cli -s=live021 run-code --filename frontend/web/tests/capture-browser-contract.js；脚本仅mock API，不能用于判定供应商连通性。截图保存在工作区 runtime/live-021-qa/，不入Git。

## ARC Review 修正
对明确4xx拒绝清除pending与旧幂等键，允许改正输入；网络/5xx结果未知继续保留原key。合成测试增加422拒绝→输入可编辑→新key提交→网络未知→同key重试；实际9项通过、capturePosts=3，asrPosts=1，TypeScript/Vite构建再次通过。
