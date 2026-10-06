# LIVE-006 MEDIA/ASR 作者变更单

状态 ready_for_review，作者 /root/eng_live002（MEDIA/ASR），独立 QA 和 ARC 尚待绑定最终SHA验收。

- 工作树 `/Users/docfat/Desktop/个人/project/直播体系FDE/.worktrees/live-006-media`；分支 `feat/LIVE-006-media`；base `43dc947`。
- 允许路径：integrations/media、integrations/asr、tests/test_media.py/test_asr.py、docs/ai/media-asr.md、本任务卡与本报告。无共享配置/worker/依赖改动；httpx runtime依赖由CFG独立提交519e313整合，当前base已有httpx开发依赖供作者测试。
- 实现接口、限制、来源、安全失败与运行命令见 docs/ai/media-asr.md。与兄弟岗位约定Pydantic model_validate恢复、逐段paid-intent包装；真实网络授权入口交队列接线，不重复建立。

## 验证与实物

真实FFprobe/FFmpeg + MockTransport共23项作者测试通过（runtime/live-006/media-tests.log）。包含真实视频提取、无音轨/损坏、协议拒清单、源路径越界、样本连续与亚毫秒尾段、音轨500ms偏移、取消/超时并join进程；ASR全局偏移、缺词/时间戳/段失败不可complete、校验和篡改、production拒离线、multipart参数、请求/时长预算、错误体脱敏、无重定向、超时/坏JSON/大响应未知不重试。

实际CLI执行产物在工作区 `runtime/live-006/media-author/`，包含合成MKV、真实16k mono WAV与分段、extraction.json，以及明确synthetic的transcript JSON。原始音源为合成正弦波，没有客户录音，也不声称这些文本是听写结果。CLI最终模型字段变化后会在交接前更新实物。

Ruff检查、格式化、范围门禁及diff --check结果随提交交接。业务源文件各自少于200行，按数据契约/受控文件/子进程/提取/传输/合并/CLI职责分开；没有全局万能文件。

## 边界与回滚

- 本轮所有HTTP由MockTransport完成，没有外部ASR访问、真实厂商验证、模型费用或预算消耗。测试里的synthetic=false仅表示走兼容协议结果结构，不是实际远程成功证据。
- 只支持具备audio/transcriptions verbose_json segments能力的所选vendor/model，不泛称所有OpenAI聊天兼容服务都可转写；真实服务需以后授权验证。
- 金额上限在无vendor计价与usage时不能证明硬封顶；本实现硬限制请求数与音频时长。
- 取消正在上传的外部HTTP不能撤销供应商已接受任务，返回未知结果，靠005持久intent禁止重复调用。
- 本次无DB迁移。回滚代码前停止接线调用，保留原片和已有runtime产物用于审计，不能删除用户资料。子进程使用POSIX现有handler进程组；独立部署FFmpeg/FFprobe需安装并检查版本。
- partial transcript应保留已知文本与缺失原因，但不能令正式分析链完整成功。具体worker状态与产物注册由统筹的独立接线任务负责。

## 独立 Review 修复

QA 发现空白文本误判 complete，ARC 要求保留缺时间戳原文并补传输边界。本修复：空白partial；缺/坏时间戳和text-only文本在unlocated/raw_text持久输出，null不编造；巨大有限时间戳未知；25,000,000字节音频前置上限；monotonic总读取期限；ASRUnknownCall from None。兼容旧缓存字段默认值。新增MockTransport测试均未外连。

修复后全套媒体/ASR测试33项（日志runtime/live-006/media-tests-fix.log），覆盖三种Unicode空白、文本保留与往返序列化、溢出、安全异常链、超大文件0请求、慢流总deadline及显式无语音。测试文件集中同一ASR契约约350行，业务源文件仍各少于200行。原作者不能自批，须QA绑定修复后的head复审。
