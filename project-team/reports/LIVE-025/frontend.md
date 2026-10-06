# LIVE-025 FE 实施与验证

FE子代理/root/eng_live001，独立副本.worktrees/LIVE-025-frontend，基线a2ef1d7；不构成独立批准。

范围：设置增加平台接入/抖音，复用AdminSession。Cookie仅密码输入的组件内存，不回填已保存值、不写storage、成功保存/清除后清空。GET/PUT/DELETE/check使用同一响应契约与expected_revision；409或未知请求结果阻止继续提交，需手动刷新核对，未自动重试。运行中与排队任务的Cookie生效规则有说明。
服务就绪/已保存/当次解析已验证独立显示。未开播可作为当次解析成功，不等于录制成功；empty/schema/network等不判Cookie过期。https_required/domain_not_allowed/unsafe_stream_url准确指向源地址策略，不建议更新Cookie或反复试录。Settings过时说明已更新：真实场次/材料/平台/ASR与演示报告/审核/评分分开，重置仅影响示例。

## 执行验证
- npm run build：TypeScript、Vite、Sites打包通过。保留既有大bundle警告。
- npm run test:sites：4/4通过。
- node --experimental-strip-types --test frontend/web/tests/platform-settings-errors.test.mjs：5/5通过。Node22.22.3；没有新增依赖或脚本。
- Edge session live025-ui，tests/platform-settings-browser.js：7类合成契约检查通过，涵盖保存不回显/清空、saved≠verified、not_live解析成功、空响应不判过期、409刷新、清除revision、无自动check。请求计数check2/save2/clear1，全为mock，未访问真实平台。
- 临时静态preview 5205经ARC登记授权，未重启5199。截图工作区runtime/live-025-qa/platform-settings.png，不入产品Git。

## 边界
没有使用用户Cookie，没有真实平台检查或采集请求，也未修改后端、模型、锁文件、CI或站点部署。独立集成验收需使用BE实际服务确认权限/私密存储/工作区隔离与worker消费；mock不能证明这些后端行为。node_modules仅使用临时本地链接，提交前移除，不入Git。

## 非作者 Review 修正
ARC指出service_ready表示完整采集执行器，不是parser门禁：现已移除连接检查对service_ready的禁止，保留“服务未就绪”状态，parser缺失交后端503分类反馈。合成浏览器配置service_ready=false仍完成显式检查，8类检查通过；检查次数仍仅2次，无平台实请求。source_auth_required改为“平台拒绝访问，请核对登录及授权条件，必要时更新 Cookie。”；needs_update显示“需要核对接入信息”，不确断过期。错误分类5/5与构建再次通过。
