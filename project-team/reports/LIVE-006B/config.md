# LIVE-006B CFG/Registry 本地变更

Owner /root/be_live004a；base74df3b1；branchfeat/LIVE-006B-registry；worktree live-006b-config。没有修改legacy provider_config.py，默认未配置/禁网。作者不自批，独立QA待ARC安排。

实现分层深合并、受控dotenv/环境白名单、逐层secret拒绝、字段来源、不可变named model和alias类型校验、v2全public快照与重试指纹。ASR沿用旧明确授权resolve；非执行能力llm/embedding/reranker/vision/detection支持typed本地huggingface/ollama/yolo描述及temperature/device/model_path/confidence，但resolve拒绝执行，不建立空壳运行器。

依赖未新增。38项合成配置/Registry测试通过、Ruff通过；测试位于runtime/live-006b/config-tests-*，包括层优先级、系统env不污染、生产隔离、低层明文secret不能被覆盖、YAML风险、引用类型、快照还原/漂移、授权前不取key、secret repr/dump隔离、描述型协议不执行及参数边界。没有读取真实密钥、外网调用或下载。

BE接口load_model_config/LoadedModelConfig.source_locator、ModelRegistry.get/validate_references/snapshot/resolve、restore_snapshot已同步；jobs接线及旧v1真实回归由其独立子任务完成。CLI环境可信与源定位选择由接线层校验，本模块不把YAML环境当可信。详细使用见docs/ai/model-registry.md及config/profiles.example.yaml。

局域网声明修订：Ollama非执行HTTP描述放宽到localhost/loopback/RFC1918私有IP/IPv6 ULA，不解析DNS、不联网；URL凭据/query/fragment限制保持，ASR HTTPS规则完全未改。新增明确深merge回归：基础127.0.0.1→local192.168.1.100，embedding cpu→mps，同时保留model与model_path兄弟字段；两描述resolve仍拒。原38项+新增1项=39项；连同legacy37项共76项通过。

独立QA发现低层base_url内嵌userinfo可被上层null覆盖后绕过最终URL校验；已在每层merge之前拒base_url的userinfo/query/fragment，并扩展client_secret等_secret/_password/_token明文键。新增5个覆盖回归，固定错误不回显QA_SENTINEL。当前44项新配置测试+37legacy=81项通过，Ruff通过，待最新head独立复审。

环境模板收尾：补齐test/staging/production空覆盖模板（继承基础默认disabled），说明正式环境仅显式私有dotenv、不读local；文档明确团队通用profile放models.yaml、本机IP/device/path差异放local.yaml，个人可先local试配。针对四个仓库环境模板逐一真实load验证canonical环境和全部disabled，staging/production locator无local/dotenv；未连接供应商。仅config/docs/report改动，无源码行为变化，待独立审查。

最终示例对齐：DeclaredRoute新增timeout_seconds（严格int，1–600，默认60），与ProviderRoute范围一致，仅描述不执行。共享profiles及文档同步。6个非法类型/范围与1个完整snapshot超时漂移拒绝回归新增，累计51项新测试+37legacy=88项通过，Ruff通过。无网络/推理/下载，等待最终head独立复审。
