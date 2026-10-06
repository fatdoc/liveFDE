# LIVE-006B：分层配置与模型注册表

本轮统一配置加载和具名模型注册，不选择供应商、不读取用户真实密钥、不下载模型。只有既有ASR兼容接口可执行；LLM、embedding、reranker、vision、detection只描述及校验，resolve明确拒绝，不能宣称这些功能已实现。没有消费者的Agent/RAG空壳目录不创建。

## 文件与优先级

由低到高：内置未配置默认 → config/models.yaml → config/environments/<受信任环境>.yaml → 开发config/local.yaml → 白名单环境变量。字典递归合并；列表整体替换；null是明确值而非删除指令，类型不允许null就报错。输入字典不被修改。每层先做secret字段和YAML安全检查，低层明文密钥不能靠高层覆盖来洗掉。

开发者可复制config/local.example.yaml为config/local.yaml；完整多模型说明在config/profiles.example.yaml，示例文件不会自动加载。它展示兼容ASR、本地Ollama LLM、HuggingFace embedding/reranker、YOLO检测的非激活profile；名称均为占位，不代表已选模型。

环境映射：dev/development→development；test→test；staging→staging；prod/production→production。环境由服务端选择，YAML不得定义environment覆盖。production/staging既不自动读开发local也不自动读.env，显式local也拒绝；仅可显式指定绝对、无符号链接、普通文件、600权限的私有dotenv。开发隐式.env位于config目录的父目录，即默认app/.env；dev/test同样要求600。

加载.env仅解析KEY=value和整行注释，可对值加同配对引号；不source、不执行shell、不做变量/命令插值、不改变os.environ。系统环境优先于dotenv。数据库/MQ等非模型设置不注入Settings，私密映射最终只保留模型key_env引用到的键。

唯一非敏感环境覆盖白名单：

| 环境变量 | 最终字段 |
|---|---|
| LIVE_MODEL_ASR_DEFAULT | aliases.asr.default |
| LIVE_MODEL_LLM_DEFAULT | aliases.llm.default |
| LIVE_MODEL_SEGMENT_SECONDS | media.segment_seconds整数 |
| LIVE_MODEL_MAX_DURATION_SECONDS | media.max_duration_seconds整数 |

其他环境值不会覆盖public配置；路由凭证只能使用key_env变量名。LoadedModelConfig私密字段排除repr/dump；任务snapshot不含密钥值或dotenv原文。source_locator返回实际使用的配置目录、环境及local/dotenv路径；未加载的可选文件返回null。来源追踪provenance只包含字段路径和builtin/base/environment/local/dotenv/server等来源名，不含值。

## Registry与引用

```python
from pathlib import Path
from live_review.core.model_config import load_model_config
from live_review.core.model_registry import ModelRegistry, restore_snapshot

loaded = load_model_config(Path('/absolute/app/config'), environment='development')
registry = ModelRegistry(loaded)
asr = registry.get('asr.default')
llm = registry.get('llm.default')
# 将来新增Agent时，注册其需要的模型引用即可先做类型校验：
registry.validate_references(['asr.default'], expected_capability='asr')
# 错写llm.default作为ASR引用会抛model_capability_mismatch。
captured = registry.snapshot()
restored = restore_snapshot(captured.model_dump(mode='json'))
# 默认allow_network=False，真实ASR不会取具体key/构建请求。
# 授权入口在本次执行明确传True才可能得到内存SecretStr，不在YAML放授权开关。
# execution = registry.resolve('asr.default', captured=restored, allow_network=True)
```

get支持alias或具名模型name，返回不可变ModelDescriptor；名字不存在明确失败，不找备用模型。aliases前缀必须匹配目标capability。所有嵌套对象frozen，models/aliases为tuple；model_dump返回独立JSON数据，不泄露内部可变容器。

ASR route保留旧ProviderRoute严格规则：disabled、offline_fixture、openai_compatible+audio_transcriptions。provider/model/base_url/key_env/timeout/请求预算等与006一致。非ASR还可声明typed DeclaredRoute：huggingface用于llm/embedding/reranker/vision；ollama用于llm/embedding，HTTP仅允许localhost/127.0.0.1/::1，否则必须HTTPS；yolo用于vision/detection。本地声明无需key或付费预算，无自动下载/连接，resolve一律model_capability_not_executable。

parameters是具名强类型对象：temperature有限0–2且仅LLM；confidence有限0–1且仅vision/detection；device限定cpu/mps/cuda/cuda:N；model_path为未执行本地声明，不允许变量、URL或..逃逸。ASR现有adapter不消费这些额外参数，因此ASR非空parameters直接拒绝，不能悄悄忽略。16k mono等已实现媒体约束仍沿用MediaConfig。

## Snapshot v2与兼容

snapshot_version=2，content含完整合并且填默认后的public配置（environment、revision、media、所有named models及parameters、aliases）；按排序JSON计算SHA256。restore先校验结构/hash，resolve重试再核整个当前配置hash；即便改未选模型也拒绝漂移，需恢复旧配置或显式新任务。trace和locator不作为模型内容指纹，但由任务接线另存并核对加载选择。

SHA256是完整性指纹而不是签名/授权。密钥值不进hash；轮换同名环境变量可能更换供应商账户，本功能不冒称解决账户身份或金额账单核验。金额只是声明，硬执行限制仍为请求数/时长。旧provider_config.py和snapshot v1未修改，新旧任务由接线层按version区分，禁止强改旧任务。

安全读取沿用64KiB文件界限、YAML深度12/事件4096、拒重复键/anchor/alias/tag、拒额外字段和非有限值；错误不回显原文、秘密或解析器堆栈。本轮所有测试在runtime/live-006b临时合成目录，未触碰用户.env或原CPB/Banana资料。
