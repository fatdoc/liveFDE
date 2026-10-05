# LIVE-003 契约基线 draft-1
状态：LIVE-003设计基线；LIVE-004已实现身份/场次/材料，其他业务仍为草案。已实现范围见implementation-status.md，实际FastAPI声明导出为openapi.json。
本目录owner ARC；已实现模块schema归BE，导出OpenAPI供后续FE客户端生成。后续分析/报告等草案在实现时逐项替换，避免永久双份权威。

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

- [实际实现范围](implementation-status.md) · [实际OpenAPI](openapi.json)。接口与运行验收分别记录，未接线的Demo不代表真实业务。
