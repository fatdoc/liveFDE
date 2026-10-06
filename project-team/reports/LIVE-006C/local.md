# LIVE-006C LOCAL 实现与作者验证

角色：LOCAL /root/be_live004a；这是作者证据，不能代替独立QA批准。范围仅local provider、独立依赖清单/下载器、local测试与文档；不修改主backend依赖锁/公共registry/数据库。

## 交付机制

- LocalASRProvider(LocalConfig) 实现async file/stream/health；惰性构造无启动下载。公开权重按固定revision预置，推理绕过hub下载器和远程代码；真实烟测通过socket.connect审计验证0出站。
- FSMN VAD → 最长片段窗口 → Nano转写/原生标点 → 可选CAM++与emotion2vec → 整场匿名speaker聚类。独立ct-punc可选。VAD内换人仍是混合embedding，无逐帧speaker变点能力。
- 原始PCM16LE/16kmono流默认5秒窗口，EOF前发partial；不是逐字原生流式。窗口与最长片段截断用vad_window，其余vad；无伪造word timestamps。
- 成功请求使用进程级单配置fingerprint缓存，跨provider实例/文件/流复用，idle60秒卸载；跨进程residency文件锁覆盖整个缓存生命周期，防双份大模型驻留。失败/取消清理，取消等待底层thread结束。模型路径变化或配置变化淘汰旧缓存；显式unload_local_models()供worker shutdown。
- 跨job进程复用依赖ARC/WORKER常驻Unix RPC集成，此LOCAL提交不把独立子进程缓存说成跨进程模型共享。
- CPU实测；cuda/auto选择逻辑测试，CUDA无本机硬件未实测；MPS明确unsupported。auto不选MPS。short speaker默认2000ms门槛，短片段null不归上一人、不参与聚类。

## 可重跑证据

工作区runtime目录均为 `runtime/live-006c/`，不入Git。

- `models/*/provision-manifest.json`：精确revision、文件体积、SHA256；没有整仓冗余下载。
- `local-smoke-base.json`：旧逐请求cache基础验证，5.616秒公开样本；coldfile48.900秒，2秒窗口首次partial43.009秒。旧结果保留，不代表当前暖缓存指标。
- `local-smoke-observations.json`：进程缓存+CAM/emotion真实模型；coldfile55.690秒，随后warmstream9.969秒，消耗5秒音频即发partial，首partial6.851秒且发生EOF前；各模型仅加载一次。
- 以上stream是尽快feed数据，耗时是计算/加载墙钟，不含模拟真实麦克风等待；线上延迟还包含实际收音时长与排队。
- `public-sample-reference.json`：官方页面与样本SHA256核对；输入公开音频的录制/合成来源未说明，模型输出非synthetic。
- `public-sample-cer.json`：一条普通话公开样本CER，不能外推产品准确率。去空白/Unicode标点，保留中文数字；reference13字“开放时间早上九点至下午五点”；file错1字7.69%；stream错1字且尾多“对”，2/13=15.38%。未用错误模型输出冒充reference。

官方reference： https://github.com/QwenAudio/FunAudioLLM.github.io/blob/72f4bee8fb7012d116a97521c9fe70d82e7ac0ba/index.html ，相邻音频与本地HF example/zh.mp3逐字节相同，SHA256 `0e64de19e4ff9a02e682955c9112f32d2317cfdbb5bc2f3504664044c993f195`。

旧observations流末0.6秒曾误分speaker-02，证据保留；按PM要求新增min_speaker_duration_ms=2000，短段unknown，不把平滑归属假定为事实。emotion中立/neutral、score1.0是模型原始最高分类分，不是人类评估准确率或校准概率保证。无可靠speaker/emotion标签，DER与emotion accuracy均未测。

## 十类数据覆盖

|类别|当前证据|结论边界|
|---|---|---|
|普通话单人短句|官方5.616秒音频真实跑file/stream，有同文件reference|仅单样本CER|
|英语|无本轮音频推理|未测|
|日语|无本轮音频推理|未测|
|中文方言/口音|无已标注样本|未测，不把模型卡语言描述当验证|
|多人轮流发言|mock向量聚类一致性|算法边界测试，真实DER未测|
|重叠说话/段内换人|无分离/逐帧变点|未测，不承诺支持|
|情绪|公开普通话样本模型返回neutral|仅推理可运行，情绪准确率未测|
|噪音/远场/音乐背景|无已标注样本|未测|
|静音/无有效语音|真实FSMN对3秒数字静音返回0segments、complete|输入是合成数字静音，非真实远场安静录音|
|长场次/断流/限额|单位测试提前输出/时长/非法PCM/取消/跨进程锁|没有真实数小时压测|

## 依赖、许可与限制

隔离env包含FunASR1.4.16、torch/torchaudio2.11.0、transformers4.57.6，固定清单位于local/requirements.txt；不安装fairseq/vllm，不加入主backend运行依赖。

公开ct-punc权重首下载在999397456/1125507622 bytes截断，被校验拦截；操作员显式Range续126110166 bytes，必须206+正确偏移，最终整文件SHA256核对。未重下整份大权重。

emotion2vec_plus_base官方模型卡license标注other/model-license，仅链接FunASR仓库，商用再分发许可未核清；不能将MIT软件许可代替权重授权。来源 https://huggingface.co/emotion2vec/emotion2vec_plus_base/raw/main/README.md 。

CAM++上游sv_chunk使用1.5秒窗、0.75秒步长并对短片段补零；2秒speaker门槛是本项目保守工程默认，不是官方准确率保证。来源 https://github.com/modelscope/FunASR/blob/main/funasr/models/campplus/utils.py 。

## 最终作者验证（待独立Review）

修复后的最终证据为 `local-smoke-final.json` 与 `local-smoke-final.log`；首次全组件 `local-smoke-full.json` 的重复标点输出保留，不能把它冒称最终结果。显式ct-punc恢复先去已有句读，保留小数、时刻、英文撇号与必要单词间隔，避免对Nano已带标点文本重复加标点。

|真实运行|耗时|结果|
|---|---|---|
|同进程首次file，五组件|62.001秒|1段，speaker-01，neutral，标点不重复|
|同配置暖缓存file|6.406秒|1段，五模型未再加载|
|随后暖缓存stream|6.167秒|2段，末0.6秒speaker=null/unavailable|
|stream首partial|4.451秒计算墙钟|已feed5000ms PCM、EOF前；不是含收音时间的端到端延迟|
|合成3秒静音file|7.332秒|真实VAD返回0segments，complete|

最终日志五组件各出现一次 `Loading pretrained params`，证明一次加载后复用。此处冷指进程尚未构建模型，没有清OS文件缓存；单次运行、不提供稳定延迟或吞吐保证。全部推理socket.connect审计出站尝试0。文件最终文字“开饭时间早上九点至下午五点。”保留实际错字；stream仍有短尾“对。”，切窗质量限制尚在。最终CER证据 `public-sample-cer-final.json`：cold/warmfile1/13=7.69%，stream2/13=15.38%，仅同一普通话样本。DER/emotion accuracy依然未测。

最终配置新增 `cache_idle_seconds=60`、`min_speaker_duration_ms=2000`；其余精确字段/约束见 `local/config.py`，device支持cpu/cuda/auto/mps（mps明确拒绝，cuda未真机验）。独立推理venv真实安装80包；最终runtime逻辑体积约5.7GB，低于7GB上限；推理结束可用盘约8.41GiB，后续下载仍需复核至少8GiB reserve。未删除任何他人文件/全局缓存。

本轮检查：`tests/test_asr_local.py` **15 passed，0 skipped**，Ruff check/format通过、git diff --check通过。单测中device使用轻量fake torch.cuda，仅检验设备选择；实际CPU模型另由上述真实smoke证明。所有直接provider烟测进程结束并显式unload，residency锁已释放，可供常驻worker独立验收。
