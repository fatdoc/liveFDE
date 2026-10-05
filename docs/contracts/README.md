# LIVE-003 契约基线 draft-1
状态：可评审的实现前设计，不是已运行 API，不生成冒充正式接口的 openapi.json。LIVE-002 仅提供工程健康端点；业务在 LIVE-004～013 实现。
本目录 owner ARC；BE 实现模块 schemas 后导出 OpenAPI，FE 生成客户端，随后将草案 schema 替换为从实现导出的契约，避免永久双份权威。

- [页面与操作](page-actions.md)：现有10页与拟实现操作的映射。
- [HTTP 协议](http-api.md)：请求/响应字段、鉴权、冲突、幂等、Range。
- [数据与状态](data-and-states.md)：关系、唯一性、版本、任务、周报。
- [草案 schema](draft.schema.json)：核心交换对象，strict JSON Schema 2020-12。
- [合成样例](examples.json)：FE/AI 正常与失败场景；全部 fixture=true。
- [校验程序](check_examples.py)：schema及跨对象/周边界/证据语义校验与负例拒绝。

运行：python3 docs/contracts/check_examples.py（jsonschema==4.26.0；本机已有，可用 uv run --with jsonschema==4.26.0 python docs/contracts/check_examples.py 隔离复现）。不调用网络模型或业务API。
实现时 request/response schema 与模块 models 分离；ID 为 UUID，展示名称不能替代关联 ID。Demo s1/plan1 等仅UI样例，不直接迁为生产标识。
该检查证明样例符合设计及部分不变量，不证明后端事务、权限或模型已实现。

Schema 中 Asset 表示资产版本视图；AssetAggregate 表示latest/published指针，AssetDraftEdit仅为编辑前后不变量的测试封套，不是实际HTTP端点。SessionTime是时间字段投影，不代替完整Session响应。
