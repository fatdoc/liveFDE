# LIVE-025 工作区平台接入设置

基线52bfde6；ARC owner；feat/LIVE-025-platform-settings；.worktrees/LIVE-025-platform-settings。
用户经PM明确授权设置→平台接入→抖音：管理员粘贴Cookie，私密保存/更新/清除，工作区隔离，连接检查仅解析不录制，实际worker消费。服务就绪、已保存、已验证必须分开；空响应不能判定Cookie过期。不回显/不记录秘密。

BE在本副本独占modules/capture、integrations/capture/providers.py、workers/capture_jobs.py及对应后端tests。FE独立子任务LIVE-025-frontend副本，只写Settings.tsx、features/capture/平台设置文件与frontend/tests/platform-settings*。ARC持有登记、契约快照、docs/capture.md、运行环境和串行集成；QA固定SHA独立审查，作者不能批准自己。无依赖/迁移更改，若必要先交ARC协调。

API契约GET/PUT/DELETE /api/v1/capture/settings/douyin；POST /api/v1/capture/settings/douyin/check。PUT {cookie:string,expected_revision:string}；DELETE {expected_revision:string}；check {source_ref:string,expected_revision:string}。读取返回revision、configured、status(not_configured/unverified/verified/needs_update/check_failed)、checked_at、checked_source、last_error及service_ready。错误白名单脱敏；修改后归unverified、clear归not_configured。检查成功含未开播也只证明当次解析成功，不证明录制成功。checked_state为live/not_live/null。

存储使用受控运行目录的工作区私密文件(0700/0600，原子写、锁、版本保护)，明确为操作系统权限保护，不宣称加密。不得放可下载对象路径。工作区流程空凭据不得回退全局env。provider在执行器开始解析时读取不可变快照，排队尚未开始的使用新值；进行中保持原快照直到结束。只解析检查单次、有上限，同工作区防重入，修改期间旧结果不覆盖新版本。

验收：权限/CSRF/隔离/秘密不回显含非法输入；save/update/clear与版本竞争；worker真正读取；检查不建任务不启动录制；失败分类；原有回归、前端构建与真实设置页。禁止重试被拦探针及变体；不操作本机Docker。只授权一次当前私密文件的真实连接检查，不自动重试录制。

用户随后试录新房间失败https_required；PM授权串行诊断/最小修复。ARC追加独占douyin_bridge.py/test_capture_bridge.py，恢复原DLR非h265的FLV偏好，但HTTPS策略优先，仅选上游明确候选，不转换scheme/扩域/放宽策略。BE在provider私有payload传递静态策略，设置check在live时校验静态源策略，不能将仅live解析成功标可录。一次授权解析诊断三个候选均HTTP，未访问CDN、未录制，旧失败具体阶段未保存不可推断。
