# LIVE-006 配置可用性小修独立 Review

Reviewer `/root/qa_live002`；仅审两份未提交文件，未改产品代码或索引。

批准以下文件字节：
- infra/providers.example.yaml：SHA256 `58411ce89c1bba5e051ebf8f1b5cca5c5308a0893b464f573b25ea5dcfb365c5`
- docs/ai/provider-configuration.md：SHA256 `0258a76948f8e25ff3d2ac41a0935238e69193c166dc410e4bee7e9d7bee0ac5`

中文模板包含合法但未启用的完整ASR profile，示例供应商/模型/地址明确为占位，key_env明确是变量名；text/vision保持关闭。文档解释YAML显式--config、同一终端export、已运行worker不自动继承变量、私有env需source且source执行Shell、数据库private.env另用、金额不等于硬费用限制或调用授权。未引入真实密钥、厂商选择或默认联网。

## 独立亲跑

- 实际load_config分别以development/production读取新模板成功。
- 每种环境中，对asr/text/vision及allow_network=False/True全部组合，resolve_execution均返回provider_unconfigured。注入禁止读取get的environ和禁止构造的httpx.Client，均未触发，证明默认inactive在密钥读取前拒绝。
- 现有配置测试37 passed in 0.15s，无skip；git diff --check通过。
- `/bin/zsh -f`实跑文档read -rs提示语法、export、unset，以及chmod600/set -a/source/set +a。只使用qa-synthetic-only合成值，断言对子进程导出及清除行为，输出不含该值；合成env仅临时位于runtime/live-006，测试结束删除。未读取真实key、未创建真实秘密文件、未构建HTTP或外连。

结论：范围内批准，无阻塞。注释与填写步骤改善可用性，行为仍默认关闭。可按上述文件hash提交，若另加简短批准记录应明确这是文档/模板小修，不变更LIVE-006真实供应商未验的边界。
