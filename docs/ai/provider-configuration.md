# 模型能力 YAML 配置与任务快照

LIVE-006 的供应商尚未选定。默认 `infra/providers.example.yaml` 的 ASR、text、vision 全部 disabled；没有默认厂商、自动发现、网络探测、环境路由覆盖或降级回退。YAML 是唯一配置策略来源，服务器受信任的 environment 决定是否为生产，不从YAML自报环境。

`infra/providers.offline.example.yaml` 仅供显式合成ASR验收，标记 provider=synthetic、model=fixture-v1；生产加载及执行均拒绝。它不能冒充真实转写、模型可用性或分析质量。`openai_compatible` 目前只是一种配置协议声明；即使填完整URL/model/key_env/预算，执行解析仍报 provider_protocol_unsupported。本轮没有真实模型调用，也不读取真实密钥。

## 接口

```python
from pathlib import Path
from live_review.core.provider_config import load_config, snapshot, restore_snapshot, resolve_execution

config = load_config(Path('/absolute/controlled/providers.yaml'), environment='development')
captured = snapshot(config)
persistable = captured.model_dump(mode='json')
# 工作线程由服务器记录读取，不能接收客户端自制快照。
restored = restore_snapshot(persistable)
execution = resolve_execution(restored, 'asr', config, environment='development')
```

当前字段结构：schema_version=1、revision、media、providers.asr/text/vision。media 为 segment_seconds（1–900）、ffmpeg_timeout_seconds（1–3600）、ffprobe_timeout_seconds（1–120）、sample_rate=16000/channels=1（固定）、max_duration_seconds（1–86400）。媒体执行器应消费这些快照值；当前配置变更不能悄悄影响重试。

每种能力各自声明 enabled、protocol、provider、model、base_url、key_env、timeout_seconds、max_requests、max_cost_usd。禁用能力不允许携带残留厂商/密钥引用/预算。显式合成ASR max_cost_usd=0；真实协议声明须完整并有正请求数/预算，但仍未实现执行。不能跨能力借用另一能力的厂商或凭证。

max_requests 是任务上限，未来真实执行器需持久记录已用次数、重试也计入；max_cost_usd 只是明确预算策略，当前没有价格查询或供应商账单核算。配置模块不能代替执行层预算账本；未完成这层前不能开启付费调用。离线任务也应在开始分段转写前检查预计段数不超过 max_requests。

## 不可变和重试

所有节点均为具名 frozen Pydantic model，未把可变dict/list藏进快照。model_dump返回独立副本；持久化的是完整无密钥值配置、snapshot_version和canonical SHA256。JSON canonical排序key、补齐默认、固定分隔符且禁止非有限值；key顺序/注释不改变hash，revision、route、预算、媒体参数变更均改变hash。

restore_snapshot核字段及hash；resolve_execution再比对捕获内容及当前YAML完整hash。变化返回configuration_changed，必须恢复原配置或显式新任务；不自动更新旧job、换vendor、增加预算。SHA256是完整性指纹，不是签名或授权；快照必须由受信任服务写入，不能信任用户提供的相同hash。

key_env仅保存变量名（如 EXAMPLE_API_KEY），不展开${...}、不接受明文api_key/password字段。未来真实adapter只能在已支持且已授权执行时取环境密钥，ExecutionRoute.api_key为SecretStr并排除序列化；本轮真实协议提前拒绝，environ参数不会读取。密钥旋转可能改变供应商账单账户，当前没有绑定账户身份，不能声称指纹解决了账户校验。

## 加载限制与错误

读取显式绝对普通文件，拒相对路径、符号链接、URL、目录/FIFO、路径环境展开。最多64KiB、2048 YAML事件、12层容器；SafeLoader加重复键/非字符串键拒绝，并在构造前拒所有anchor/alias/显式tag，避免unsafe tags与别名扩张。不允许额外字段、类型强转、不合理数值、NaN/Inf、URL用户名密码/query/fragment、非HTTPS/非443及路径逃逸。没有YAML include与环境覆盖逻辑。

load/restore公开错误为ProviderConfigError固定代码，不附解析器原文、配置值、路径或秘密。业务handler需映射为安全任务失败，勿捕获后返回伪成功。endpoint校验是声明格式检查，并非未来网络SSRF防护已完成；任何真实adapter仍须设计DNS/IP/redirect出口策略。

测试：`uv run --project services/backend pytest services/backend/tests/test_provider_config.py -q`。新增依赖PyYAML==6.0.3锁入uv.lock；[官方SafeLoader文档](https://pyyaml.org/wiki/PyYAMLDocumentation)为基础，本实现增加上述资源/重复键限制。未读或改 Banana/CPB 配置与密钥。
