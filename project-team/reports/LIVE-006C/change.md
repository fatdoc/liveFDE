# LIVE-006C 本地变更单

基线 `840d46182c3637bc95032751c463f57ef95b1b7e`。无 Git remote，本轮没有 GitHub PR、部署、发布或客户验收。独立QA为 `/root/qa_live001`，产品验收为独立 PM 任务 `01a10b7c-30e0-7fa3-9545-0001d85a33b3`，作者和审阅者不冒用Git身份。

## 改变的行为

现有 React ASR设置从演示变为真实管理员登录、PostgreSQL偏好保存、revision冲突、就绪检查、材料上传、任务提交和持久结果查询。首次保存之前不允许试用，防止任务暗用变动的YAML默认。其他页面仍为Demo。

Python统一file/stream/health网关接入真实本地FSMN/Nano/CAM++/emotion2vec/ct-punc，以及腾讯文件TC3和实时V2适配器。本地专用Unix进程跨job复用五模型，取消必须确认底层清理。网络权限与保存设置分开；云调用先持久化意图，未知结果不自动重放；本轮没有实际云调用。

新增唯一迁移 `0005_asr_settings`，延续0004；settings表按workspace存偏好与revision。共享模型注册表兼容已有v1/v2快照，ASR默认策略另作快照。M4A/AAC增加实际FFprobe格式校验。API/OpenAPI、WS协议、部署和限制见 `docs/asr.md`，源码/依赖清单见本目录manifest。

## 独立审查与修复

| 模块 | 作者提交 | 集成/证据 |
|---|---|---|
| Tencent | a3464b5 | 独立18协议模拟；集成49de69d |
| React设置 | 9c1bc15 + b01a267 + 12b1c54 + f948834 + 717cb52 | 独立diff批准；集成49de69d/dda195f/751c331 |
| WS | 37f70b8及IPC取消增量 | 独立PG19用例；集成5143069/66e0683 |
| 常驻worker | 830a2db + 91f5629 + 4964a0b | 独立20 Unix测试和原失败探针通过；集成66e0683 |
| LOCAL | 8521c0c + f05bcd2 | 独立21单元通过；集成1d38b6f |
| 组合后端 | 1d38b6f | 独立48项PG/策略/WS回归、旧快照逐字/hash一致 |

IPC最初在socket写partial期间提前ACK停止，独立探针复现后加aclosing保证native/生成器清理完成再释放锁。LOCAL最初VAD有语音但ASR空输出会被误标完整，现明确失败；真正无VAD仍合法静音。两项P1均由作者修复后独立复审，不用原有测试通过替代新探针。

首次未保存设置revision0默认漂移、无云授权仍被禁用fallback拦截两项P2均已修复。真实结果保留识别错字、未知说话人、无置信度等限制，不加工成理想输出。

## 实际验证

- 主版本完整后端顺序回归：313 passed / 0 skipped / 0 failed，279.67秒，独立新PG15480库。`runtime/live-006c/integration/0b93a2f82eae48d49120eba63547716b/pytest.xml`及log。明确排除broker专用测试，不宣称重做RabbitMQ部署验收。
- 前一轮 `integration/45086618b3a14da390818bb4ff5bf1eb` 为263通过/1失败：ASR API测试遗留自己工作区的Outbox，dispatcher测试取到它。1187a82补fixture teardown清本fixture工作区Jobs/Outbox，未放松断言；上述313项是包括原失败用例的完整顺序重跑，旧失败记录保留。
- 工程守卫36通过；Ruff/diff检查通过；前端TypeScript/build及Sites4/4通过。已有Starlette httpx弃用提示、前端大chunk警告保留，不算失败也不抹去。
- 真实直接provider五组件：冷file62.001秒、暖file6.406秒；五模型各只加载一次；socket.connect审计0出站。公开样本file CER7.69%、stream15.38%，不是总体准确率；DER/情绪准确率未测。
- 主版本真实HTTP上传→持久job→独立处理子进程→常驻worker→查询：两次file成功，端到端60.781/18.918秒。第二个job仍同一worker，没有再加载五模型。`runtime/live-006c/smoke/f0271ec3261642a592362602afcfb3df/observations.json`及同目录worker日志快照。
- 同一环境真实WS按1:1节奏送PCM，首partial11.640秒（EOF前），总15.331秒；完成事件与已落库结果相同。以上端到端指标含通信/排队/收音，与直接provider快喂计算耗时不同。
- 该早期端到端脚本的 `cloud_calls:0` 是预设字段，不是出站审计。执行保存了local_only、无云授权；feed434把后续脚本改为明确策略字段和未instrument声明，HTTP/WS禁环境代理。直接provider审计是单独证据，不混用。
- PM实际IAB查询file及WS通过，确认尾段speaker未知；没有为产品验收重复请求模型。FE另一次真实GUI上传成功，任务149e4df6-9d60-4f24-b6de-b7056f50143c，见ui-browser.md。首次revision0新账号GUI未测，独立API+代码门禁已验，明确不混用。
- 最终文案集成751c331后重新TypeScript/build成功（5.58秒）及Sites4/4通过，日志frontend-final-build.log/frontend-final-sites.log；纯文案无需重跑后端或模型。

## 用户可打开的入口

开发预览 `http://127.0.0.1:5196/settings`，API `http://127.0.0.1:8196`。本轮合成验收账号在工作区 `runtime/live-006c/ui-account.json`（0600，勿入Git或发布）；首次设置专用账号另在 `ui-first-account.json`，没有改现有账号。查询真实任务：

- file：`8478102e-5a9a-4cc2-ab85-7ad712c498bc`
- 第二file：`c2a548d7-f5d7-49db-acf6-cca19b9f3176`
- WS：`bfe3a7b9-f780-4fd4-b7f2-826d597a1501`

以上同一个preview数据库，无需重新调用模型即可查看。运行输出、日志、数据库、权重均在工作区runtime，旧CPB/旧轮次数据库未动。独立worker空闲60秒卸载权重；保留预览不代表自动后台开发。

## 限制与恢复

腾讯缺凭证/请求与金额预算，真实云调用为未验证；协议mock不能替代。直传规范化WAV≤5,000,000字节约156秒，未接长录音COS/URL。金额仍是授权声明，未做厂商实际账单核算。CPU已测，CUDA无硬件、MPS不支持。emotion2vec权重商用/再分发许可待核清。输入十场景逐项见quality-matrix，最长真实有效语音仅5.616秒，不宣称数小时能力。

回滚先停止本轮API/worker并确认无活跃推理，不删除运行媒体或旧库；代码按本地提交反向撤销，不破坏性downgrade有数据的0005。正式生产需已有dispatcher/worker与部署验收，开发BackgroundTasks不是生产持久队列。未启动LIVE-007及后续评分/报告/采集。

最终代码SHA `751c331e834823021db6ba85bda410e5bd1fd04a`，代码tree `b1f19ae8f4b3117545b22d841c8a34abf6c2c6d3`。manifest.json列基线至该代码提交的91个精确路径/大小/哈希，不包含随后纯收尾报告自身，避免自引用哈希。独立最终tree核对与PM范围结论见qa.md/product-acceptance.md及任务看板；收尾提交只归档事实性文档，不改已批准代码。
