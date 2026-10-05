# LIVE-006 配置独立审查

Reviewer `/root/qa_live002`；批准配置源码 SHA `519e313c426c58ae4fc46ea9e515ae9c097c9913`（含 e9394fd）；基准 `43dc947`；工作树 `.worktrees/live-006-config`，审查前后均 clean。

结论：配置模块范围批准，无阻塞发现。不是媒体适配器、正式任务接线或真实供应商验收。

## 独立亲跑

- `uv run --offline --frozen --project services/backend pytest services/backend/tests/test_provider_config.py -q`：37 passed in 0.09s，无 skip。
- 同环境 Ruff 检查 provider_config.py/test_provider_config.py：通过。
- 独立脚本追加验证 JSON 快照往返、预算/路由更改拒绝、明文 secret 字段错误脱敏、递归 alias 拒绝、布尔型采样率/请求数拒绝、FIFO 非阻塞拒绝：全部通过。合成配置临时文件位于本轮 runtime 并自动删除。
- diff --check 通过；没有源码修改、数据库访问、网络调用或真实凭证读取。

## 审查事实

SafeLoader 前预解析拒绝 tag/alias/anchor，限制64KiB/事件数/深度；重复及非字符串键拒绝。嵌套节点为 frozen 模型，序列化副本不反向修改；恢复校验 canonical hash。公开 load/restore 错误固定代码且不带原文。

enabled=false 可留完整 openai_compatible profile；protocol=disabled 表示空 profile，两者语义已在文档说明。ASR 显式 audio_transcriptions；text/vision resolve 拒绝，不跨能力回退。allow_network 默认 false 且在读环境之前拒绝；显式允许后仅解析 SecretStr，排除 repr/序列化。协议配置层没有网络调用。

route/media/预算变更触发 configuration_changed，需恢复原配置或显式新建任务，不能静默更换旧任务策略。金额仅预算声明，不能宣称精确计费/货币硬限；请求次数与音频时长硬限制、恢复次数账本必须在 MEDIA/ARC 最终验收确认。

## 后续验收边界

配置格式验证不等于 SSRF 出口策略；实际 HTTP adapter 必须验证重定向和错误脱敏。需检查正式入口不会将客户端 allow_network 直通授权，不接受任意客户端自造 snapshot；快照 hash 不是签名。生产 fixture 禁用、恢复快照固定、实物 WAV/分段时间、取消子进程、实际请求次数持久化仍待最终集成 SHA。真实供应商没有授权，后续仅 MockTransport。
