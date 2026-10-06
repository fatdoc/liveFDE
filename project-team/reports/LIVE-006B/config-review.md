# LIVE-006B CFG 独立 Review

Reviewer `/root/qa_live002`。初审SHA `ddc64db166a3076ceb1199bc552cdf8817a69571`，worktree live-006b-config clean。**当前不批准，等待逐层秘密检测修复。**

## 亲跑

38项新配置/Registry + 37项legacy：75 passed in 0.36s、无skip。Ruff通过。

额外独立探针在runtime/live-006b合成临时目录中，将完整profiles.example.yaml实际作为models.yaml，在development/staging/production加载。HF embedding/reranker、Ollama LLM、YOLO detection typed descriptor可合法声明；snapshot JSON往返一致。所有非ASR resolve明确model_capability_not_executable，ASR inactive明确provider_unconfigured，即便allow_network=True也不执行。禁止httpx.Client与subprocess.Popen陷阱均未触发。

系统环境合成值优先于dotenv；仅key_env引用值私密保留、无关秘密不保留，repr/model_dump/snapshot不含合成值。os.environ前后完全相同。独立deep_merge嵌套兄弟/列表替换/null及修改结果不污染输入验证通过。只用合成秘密，未读真实.env、未联网/下载/访问DB。

## 阻塞

逐层URL秘密可被覆盖隐藏：models.yaml内 `models.asr_unconfigured.route.base_url: https://user:QA_SENTINEL@example.invalid/v1`，local.yaml将该base_url置null。load_model_config成功返回disabled route。read_yaml的reject_secret_fields仅检查字段名和插值，不检查每层URL userinfo/query/fragment；最终schema看不到已覆盖秘密。独立复现成立，违反“每层拒秘密，包括被覆盖内容”。已发作者修复并补回归，公开错误不得回显秘密。

另外请作者核常见client_secret等凭证字段别名不能靠覆盖洗掉；每层检测需按明确禁止秘密规范执行。此报告不是要求宣称能识别任意普通文本中伪装的密钥。

## 其余审查与边界

frozen模型/tuple保存公开全量配置，完整指纹含所有模型/参数/aliases/environment；恢复核hash，resolve核漂移。ASR沿旧ProviderRoute，V1原模块未改，实际任务版本分支与旧缓存/unknown兼容仍待JOBS/PG验收。环境白名单不含grant；production/staging不隐式加载devlocal/dotenv，显式local拒绝；显式dotenv仅安全文件解析。没有LLM/agent/RAG/embedding/reranker/detection执行、没有权重下载或服务探测。

## 修复后批准

**批准精确SHA `86054555dd57f666169145786e230bb13f81d080`**，替代不批准的初审ddc64db。新增每层base_url userinfo/query/fragment禁项与_secret/_password/_token/secret_key检测，安全错误不回显。独立重跑最初低层userinfo被高层null覆盖复现，现明确endpoint_credentials_forbidden；回归81 tests passed in 0.34s（44新+37legacy，无skip），Ruff/diff通过，工作树clean。

另审PM要求的LAN声明增量309a3f6：Ollama HTTP仅localhost、loopback、RFC1918及IPv6 ULA地址字面量；不解析DNS、不建连接。独立范围探针确认192.168/10/172.16/fd00允许，8.8.8.8/169.254.169.254/172.32/普通域名拒绝。深层覆盖仅Ollama base_url与embedding device的回归保留模型/protocol/model_path兄弟字段，resolve仍unsupported，未下载权重。

该批准仅CFG模块及注册声明范围，V1/V2实际任务兼容、正式入口、PG和根验收driver仍需后续组合QA；不承诺真实模型可用性或计费。
