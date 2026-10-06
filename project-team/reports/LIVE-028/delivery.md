# LIVE-028 大模型设置与最小连接测试

用户原设置页没有大模型配置入口，本轮在既有React设置中增加独立『大模型配置』页签，接入当前工作区真实后端保存。基线8062931；任务、接口与目录范围在6b85588登记。ARC集成/运行，FE/BE分别在独立工作副本实现，QA非作者固定SHA审查。

接口地址/模型名/超时可保存和重新读取。API密钥只写不回显，省略保留、替换更新、清除删除；保存后输入框清空且显示已配置状态。保存零模型请求，连接测试为单独明确按钮，显示未测试/成功/失败/未知及时间和供应方usage。未保存编辑不能测试。ASR失败原记录保留，不通过配置页自动触发转写。

通过Model Loader/ModelRegistry生成workspace的有效LLM视图，不修改共享ASR配置。0700目录/0600秘密文件在材料下载路径外，修订号CAS、进程锁、原子配置指针与不可变secret版本避免密钥和配置错配；成功更新/清除后清理旧secret。请求意图在网络前持久化，同UUID不重发、跨revision墓碑保留，同revision未知结果禁止换UUID再发；应用重启遗留checking保守unknown。测试时配置改变，不回填旧结果。

普通ProviderRoute HTTPS443规则保持；HTTP只在development且命中本机服务端精确base URL白名单允许，web不能自行授予例外，production拒绝。每次测试校验全部DNS结果为公网、TCP固定目标IP、HTTPS验证原hostname证书；共享总deadline覆盖DNS/连接/响应，响应体64KiB上限，禁止redirect/代理/自动retry。固定合成prompt Reply with OK.、max_tokens32、stream=false，一次POST chat/completions，不请求/models、不发送业务材料。max_cost_usd兼容字段不等于实际计费硬上限，usage仅供应方报告。

## 验证与运行边界

最终功能SHAdbdbc146de54c6750052218ca203bea4cd91fa7f已获QA-02非作者工程批准。作者164离线测试通过；QA独立原145项+resolver12项，修复后重验设置18项、连接46项（重叠不累加），FE4单测/13组合成Edge通过；根42工程、Ruff、目录门禁及组合构建通过。API新增用例替换current_admin但使用真实MutationAdmin/CSRF，不能称新增原生PG端到端；远程CI另覆盖原生PG/MQ。独立发现P1历史缓存覆盖未知状态、P2不完整HTTP framing误判成功均修复且原复现关闭，证据runtime/live-028/qa-fixed-review.md与qa-findings.md。PR19最终CI和部署结果随闭环记录；运行实测仅ARC在已审版本执行一次合成连接，结果无论成功失败均保留，未知不重试。runtime/live-028/baseline.json记录原ASR/采集配置及model YAML指纹；部署后应保持一致。最终精确SHA、CI、进程、真实结果和页面证据见runtime/live-028/closure.json，不以代码测试代替真实连接验收。

业务分析仍未接入：analysis_enabled=false；未生成复盘报告或评分，没有新增ASR调用。本轮配置与最小连通成功（若实测成功）不代表真实业务分析质量。回滚仅代码，先确认空闲再串行切回原进程代码；保留私密配置和既有材料/失败记录，不启动全队列或自动重试。

最终CI原37510320267/37510326022均保留575通过/1失败：deadline关闭socket后EOF被framing误分类，未知防重仍生效。增量修复使总deadline优先，原慢读断言未放松；QA connection46通过，另4组真实socketpair/真实时钟交叉复现正常截断与约1.002秒超时均正确且外部请求0，见runtime/live-028/qa-deadline-review.md。旧失败不以新结果覆盖；最终提交CI状态以closure为准。
