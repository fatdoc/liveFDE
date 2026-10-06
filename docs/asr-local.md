# LIVE-006C 本地 ASR

本实现使用 FunASR 1.4.16、PyTorch/Torchaudio 2.11.0、Transformers 4.57.6。重依赖仅在独立推理环境，不进入普通后端依赖。完整固定版本位于 `integrations/asr_gateway/local/requirements.txt`。

## 部署与配置

操作员先运行 `local/provision.py MODEL_ROOT` 下载指定 revision 的公开文件；下载脚本与推理入口分离。文件逐一检查体积，LFS 文件检查上游 SHA256，生成本地 manifest。默认整个 runtime 最大 7,000,000,000 字节，下载后必须至少保留 8 GiB 磁盘。中断 `.part` 要操作员检查，默认不续传；显式 `--resume` 只在HTTP 206及正确Content-Range时追加，最后重新核全文件SHA256，不重复下载完整权重。不得提交权重、样本、推理输出或密钥。

本轮独立环境：`runtime/live-006c/.venv`；模型根 `runtime/live-006c/models`。部署可配置绝对根路径，以下子目录固定：

|组件|子目录|作用|
|---|---|---|
|FSMN|fsmn-vad|语音区间|
|Fun-ASR-Nano|Fun-ASR-Nano-2512|中文/英语/日语转写与原生标点|
|CAM++|campplus|192维声纹embedding，无真实身份识别|
|emotion2vec+|emotion2vec_plus_base|声学情绪类别与模型分数|
|CT-Transformer|ct-punc|独立可选标点恢复|

`LocalConfig(model_root=..., device="cpu")` 默认使用 Nano 原生标点；显式设置 `punctuation_model="ct-punc"` 才启用独立模型。`punctuation=False` 仅关闭额外标点恢复，Nano 自身生成的标点不会删除。模型不自动下载；构造时读取本地 YAML，传入 `model_conf` 绕过 FunASR hub resolver，tokenizer/LLM 初始化均定位本地子目录，禁用远程代码及更新。

`device` 支持 cpu/cuda/auto/mps。auto 只在 CUDA 实际可用时选择 CUDA，否则 CPU；显式 CUDA 缺硬件会报 `local_cuda_unavailable`，显存不足报 `local_device_out_of_memory`，不静默回退。MPS 明确报 `local_mps_unsupported`，不能将 Mac 上 available 当作推理兼容证据。本机 CUDA 未实测。

## 输入输出与边界

文件输入是预处理后的 16kHz 单声道音频；超请求时长在模型加载前拒绝。FSMN 切段，Nano 按最长15秒边界解码；时间戳来自 VAD；窗口/最长段截断标记vad_window，**不提供伪造逐字对齐**。空静音文件可以产生成功但空 segments。所有请求按输入时长限额，文件默认最长600秒、上限由公共契约管理。

WebSocket/provider流输入为原始PCM16LE、16kHz、mono，单chunk不可大于窗口大小，允许奇数字节跨chunk但总长必须偶数。默认累计5秒进行VAD+Nano，每个窗口完成后立即发 partial，不等待EOF；最终对整个连接embedding统一聚类，发 final 与 completed。它是窗口增量识别，非逐字实时解码，窗口边缘可能截断词语；partial时说话人未定，EOF后的final才有整场speaker标签。音频buffer小于两窗口，状态每连接独立；服务端须在断连时关闭迭代器。

说话人通过整场embedding余弦距离平均链接聚类，默认相似度阈值0.65，最大16组；标签按首次出现排序。声纹默认少于min_speaker_duration_ms=2000ms的片段不参与聚类，speaker_id=null，不强行分给上一人；情绪少于400ms保持null；一个VAD片段内部若中途换人，将提取混合embedding，当前没有逐帧说话人变点检测，不能声称已可靠拆分内部换人。情绪是音频分类结果，无心理诊断含义。ASR词置信度未知，保持null。

## 内存与取消

模型根的 `.inference.lock` 使用fcntl排他锁，覆盖加载、推理及卸载，支持不同job子进程共享根时串行运行。模型按规范化model_root与配置fingerprint进行进程级单配置缓存，连续file/stream请求及不同provider实例复用同一套已加载模型。进程内锁串行推理；跨进程residency锁直到idle卸载才释放，防止其他进程同时加载第二份。默认cache_idle_seconds=60，无请求60秒后Timer在拿到进程锁时卸载；换配置淘汰旧缓存，显式async unload_local_models()用于优雅关闭。成功请求不卸载，失败/取消后清理。不同子进程无法共享Python缓存，跨job复用须由上层常驻local_worker转发，不能仅靠此模块宣称实现。本地锁等待可取消，默认300秒超时。线程推理开始后的async取消等待该段结束后再清理；独立job进程组终止由外层worker负责，OS释放文件锁。文件锁是同一主机本地文件系统机制，不是跨主机GPU调度器。

`health` 只检查依赖可发现、必要文件及设备，ready代表已配置可尝试；reason=`provisioned_lazy_not_loaded` 明示未预热，不冒称模型已完成真实推理。

## 验证状态

单元测试中使用的mock仅验证边界、流提前输出、speaker聚类及取消锁行为，不计算识别准确率。真实样本smoke、模型耗时、存储体积见本轮验收报告；无人工标注数据时CER、DER及情绪准确率一律未测。

来源：FunASR官方仓库 https://github.com/modelscope/FunASR ，各公开模型仓库及固定revision在 `local/provision.py`。模型授权以各仓库模型卡为准，软件包许可不等于所有模型权重许可。

模型卡许可核查：Nano与CAM++模型卡标注Apache-2.0；emotion2vec_plus_base标注other/model-license，链接仅指向FunASR仓库，商用再分发许可未核清，不能把软件包MIT许可替代权重许可。来源 https://huggingface.co/emotion2vec/emotion2vec_plus_base/raw/main/README.md 。

声纹最短片段阈值2000ms是保守工程默认，非官方质量保证。上游CAM++ sv_chunk使用1.5秒窗、0.75秒步长并对短片段补零，没有给出通用准确率所需最小时长。我们没有采用上游把很短片段归给邻人的smooth策略。来源 https://github.com/modelscope/FunASR/blob/main/funasr/models/campplus/utils.py 。

已验证重跑入口：在backend src可导入的环境运行 `python -m live_review.integrations.asr_gateway.local.smoke MODEL_ROOT OUTPUT_JSON --observations --punctuation`。该入口直接禁止socket.connect并执行冷file、暖file、暖stream，结束显式卸载缓存。它不会下载；输入固定为预置公开example/zh.mp3。评分指标不在smoke里伪造，单样本reference/CER证据在本轮作者报告。

完整性：只有明确VAD `value=[]` 才按无语音返回空成功。已检出语音但Nano无文本，抛 `local_asr_empty_for_speech`（混合正常/空段也失败）；不把转写丢失标为complete=true。VAD响应缺失/非法、语音片段短到无法处理均有明确错误。
