# LIVE-006C 统一ASR Service/Gateway

状态：done（基础版范围，质量/真实云缺口明确保留）；base840d461；最终代码751c331，独立QA与PM通过。用户经PM明确授权本地FunASR与腾讯file/实时V2和可用设置页。以下是原任务分工，最终实现/证据/限制以reports/LIVE-006C/change.md为准。

1. 官方审计与契约：统一async file/stream/health、时间/说话人/情绪/完整性来源，未知为null；模型配置复用006B，音频复用006，持久任务与未知调用保护复用005。
2. LOCAL /root/be_live004a：.worktrees/live-006c-local；integrations/asr_gateway/local/、tests/test_asr_local.py、docs/asr-local.md、本轮local报告。VAD/Nano/CAM++/emotion2vec/punct；独立runtime安装/缓存先估算，禁止运行时自动下载/上传。
3. TENCENT /root/eng_live002：.worktrees/live-006c-tencent；integrations/asr_gateway/tencent/、tests/test_asr_tencent.py、docs/asr-tencent.md、本轮腾讯报告。file TC3与实时V2官方签名/协议分开，未知付费不重放。
4. UI /root/qa_live002转FE：.worktrees/live-006c-ui；frontend/web ASR设置/登录/试用链与本轮UI报告，最终操作指南汇入docs/asr.md不另建空说明。持久设置来自API，不用localStorage冒充。不能批准本轮自己的UI。
5. ARC /root：公共contracts/factory、006B registry扩展、modules/asr/鉴权设置/API/WS、唯一0005迁移、worker接线、backend依赖锁、独立环境/验收脚本/docs/asr.md与报告。单owner串行集成，不修改员工own paths。
6. 独立QA后续由非本轮作者岗位检查所有组合，PM产品与浏览器验收，不修改共享文件。

全部项目产物在本工作区。006C单独PG15480、API8196、UI5196（先探端口），runtime/live-006c。旧006B/CPB/客户资料不动。前端其余页面保留Demo，不扩007画面/报告。

默认local_only。出站必须cloud_allowed、逐任务授权、明确非空预算；fallback还必须allow_cloud_fallback，未知请求永不自动fallback/retry。允许所需腾讯凭证的有无检查与隔离读取，不打印/不读取无关秘密；具备完整配置预算才可各一次file/实时≤10秒smoke，不盲重试。公开本地依赖/权重下载仅本轮runtime，磁盘现18GiB，先估算、预留至少8GiB空间，初始缓存上限6GiB，不删他人文件。

验收：独立PG迁移/隔离/revision冲突，真实本地smoke与可用设置页登录/保存/刷新/实际provider变化；协议MockTransport明确标记，真实云缺项明确未验证。10类矩阵与CER/DER/emotion/耗时有可靠reference才报，不编造准确率。完成需代码SHA、独立批准、PM范围验收与文件清单。

PM范围补充：文件试用必须支持M4A/AAC，ARC持有materials schemas/service/validation及新tests/test_asr_formats.py，原格式校验继续保留。UI只增强本轮格式选择。

TENCENT a3464b5完成后，/root/eng_live002转BE-WS独占modules/asr/stream.py、tests/test_asr_stream.py与reports/LIVE-006C/stream.md，在同副本取root共享接线依赖后实现。ARC不并写stream.py；router注册由ARC处理。
