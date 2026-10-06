# LIVE-028 大模型配置、一次最小连接测试与可见部署

基线80629315022f8772743a06a09eae003e597a78ec。用户通过PM授权『设置里面添加大模型配置填入』及既有端点的debug，最终部署5199，含已审PR18，不追加ASR。本轮一次真实最小合成LLM调用由ARC独占；无真实录音/转写外发，无下载、自动重试或全队列启动。原ASR失败保留。

ARC集成副本.worktrees/LIVE-028-llm-settings；BE/FE分别.worktrees/LIVE-028-backend和LIVE-028-frontend；runtime/live-028运行证据。一owner一分支，FE仅Settings.tsx、features/llm/与两测试；BE仅登记的backend/core/main/tests及openapi快照；ARC持docs/任务/scope/状态与运行；QA固定SHA安全审查与合成验证，真实连接结果另验。

沿用Config Loader/ModelRegistry建立workspace的有效LLM视图，不修改全局ASR配置；既有workspace私密设置模式0700/0600、修订号/进程锁/原子写，不进可下载storage，不暴露密钥。不得创建第二套模型配置系统。普通ProviderRoute HTTPS/443规则保持；新增development/test专用LLM调试route只在运行时命中服务端精确端点白名单后可执行。白名单来自本机配置，当前仅用户授权端点，UI无任意HTTP开关。所有目标拒绝私网/元数据/重绑定/redirect、限响应/总时限、不采用系统代理、无自动重试。安全Review独立。

设置新增『大模型配置』独立页签；接口地址/模型名/密钥/超时可编辑。密钥只写、可保留/替换/清除，保存后清空输入、已配置状态；URL和模型刷新保留。保存不请求网络，测试按钮明确最小合成请求，显示未测试/成功/失败/配置已变更需重测、时间及usage（若提供），错误只安全码映射。无业务分析消费者，不宣称接入复盘分析。

## API冻结（前后端共同实现）

路径/api/v1/llm/settings；GET CurrentAdmin；PUT/DELETE/POST check要求MutationAdmin与CSRF/Origin。
GET/PUT/DELETE/check响应统一：revision:string, base_url:string, model:string, timeout_seconds:number（1–120整数）, configured:boolean（密钥状态）, status:not_configured|unverified|checking|verified|check_failed|unknown, checked_at:string|null, last_error:string|null, usage:{prompt_tokens?:number,completion_tokens?:number,total_tokens?:number}|null, debug_http:boolean, analysis_enabled:false。不返回key、模型原始文本或原始错误。
PUT {expected_revision,base_url,model,timeout_seconds,api_key?:string}，省略key保留，空白key拒绝。DELETE {expected_revision}仅清密钥，保留其他字段且失效测试。check {expected_revision,request_id:UUID}，预先持久化请求标记；同id结果缓存/未知不可自动再发，测试中的设置变化不能回填旧结果，配置变更重置测试状态。明确保存成功但未测试。新未配置默认URL/model为空、timeout60。

ModelRegistry仍不将llm标为分析可执行。新增仅diagnostic适配器，固定chat/completions最小合成内容，max_tokens有界/stream=false，一次POST；响应结构及usage有界验证，未知请求不重放。时间限制须覆盖DNS/TCP/TLS/响应，HTTPS验证证书与域名且连接固定公共IP。

验收：隔离workspace、鉴权/CSRF、revision并发、secret不回显/不入日志、保存零网络、未知结果不重试、SSRF/HTTP例外/redirect/timeout/响应体上限、真实Edge保存/刷新/密钥状态与合成UI；独立固定SHA+CI通过再串行部署。用户真实端点/密钥仅运行私密文件，不写公开测试/fixture。ARC部署确认空闲保全配置，不重录/ASR；最终一次真实合成连接测试在已审运行版本，记录真实结果和限制，无自动重试。
