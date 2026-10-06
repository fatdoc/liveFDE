# 大模型配置与连接测试

设置 → 大模型配置由管理员管理当前工作区的接口地址、模型名、API密钥和1–120秒超时。保存仅保存配置，不请求模型；省略密钥保留当前密钥，替换写新值，清除删除密钥但保留接口与模型字段。密钥保存后输入框清空，读取接口只返回已配置状态。

连接测试是独立的手动操作：固定合成提示词 `Reply with OK.`，一次chat/completions、stream=false、max_tokens=32；不发送任何录音、真实转写或业务材料，不做自动重试。成功只证明该配置完成一次最小请求，不代表复盘、评分、长文或视觉分析已接入。usage若提供，属于供应方报告的token数，不等于本系统已落实美元计费硬上限。

测试状态绑定配置revision，保存/清除后旧结果失效；未保存编辑不能测试。超时、连接中断、响应不完整等可能已被供应方处理，标记unknown后不得自动再次提交。先刷新读取状态，同request_id只能取回已记录结果；配置改变也不删除历史请求标记。应用重启留下的checking保守转unknown。

API为 `/api/v1/llm/settings` GET/PUT/DELETE及POST `/check`，沿用管理员身份、Origin/CSRF、workspace隔离和修订号冲突检查。配置通过既有Model Loader及ModelRegistry生成当前workspace的有效LLM视图，不修改全局ASR模型文件、默认ASR别名或运行指纹。密钥保存在下载目录之外的0600私密文件，父目录0700；公开响应、错误及日志不得包含密钥或上游原始内容。

普通OpenAI兼容配置保持HTTPS/443。HTTP调试仅development且命中服务端 `LIVE_LLM_DEBUG_HTTP_ENDPOINTS` 中精确base URL时允许；web填写一个HTTP地址不能自行获得例外，生产环境拒绝。该列表属于本机受控运行配置，交付默认空。每次请求重新校验目标，拒绝非公网IP/重定向，DNS全部结果检查后实际连接固定IP，HTTPS仍校验证书与原域名；限制总时长和响应体，不继承系统代理，不自动切换地址或重试。

当前没有调用LLM生成复盘报告的业务消费者；`analysis_enabled=false`。本地ASR和直播采集的验收状态分别管理，配置成功不能替代这些验收。
