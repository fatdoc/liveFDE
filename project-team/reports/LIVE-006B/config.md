# LIVE-006B CFG/Registry 本地变更

Owner /root/be_live004a；base74df3b1；branchfeat/LIVE-006B-registry；worktree live-006b-config。没有修改legacy provider_config.py，默认未配置/禁网。作者不自批，独立QA待ARC安排。

实现分层深合并、受控dotenv/环境白名单、逐层secret拒绝、字段来源、不可变named model和alias类型校验、v2全public快照与重试指纹。ASR沿用旧明确授权resolve；非执行能力llm/embedding/reranker/vision/detection支持typed本地huggingface/ollama/yolo描述及temperature/device/model_path/confidence，但resolve拒绝执行，不建立空壳运行器。

依赖未新增。38项合成配置/Registry测试通过、Ruff通过；测试位于runtime/live-006b/config-tests-*，包括层优先级、系统env不污染、生产隔离、低层明文secret不能被覆盖、YAML风险、引用类型、快照还原/漂移、授权前不取key、secret repr/dump隔离、描述型协议不执行及参数边界。没有读取真实密钥、外网调用或下载。

BE接口load_model_config/LoadedModelConfig.source_locator、ModelRegistry.get/validate_references/snapshot/resolve、restore_snapshot已同步；jobs接线及旧v1真实回归由其独立子任务完成。CLI环境可信与源定位选择由接线层校验，本模块不把YAML环境当可信。详细使用见docs/ai/model-registry.md及config/profiles.example.yaml。

局域网声明修订：Ollama非执行HTTP描述放宽到localhost/loopback/RFC1918私有IP/IPv6 ULA，不解析DNS、不联网；URL凭据/query/fragment限制保持，ASR HTTPS规则完全未改。新增明确深merge回归：基础127.0.0.1→local192.168.1.100，embedding cpu→mps，同时保留model与model_path兄弟字段；两描述resolve仍拒。原38项+新增1项=39项；连同legacy37项共76项通过。
