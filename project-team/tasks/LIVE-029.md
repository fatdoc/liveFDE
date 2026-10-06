# LIVE-029 材料转写选择、历史收起与长录制

基线 a69888ac7af860dfc475f6bb57bd4d298425bd77。用户通过PM授权三项功能开发、独立审查、CI、部署当前5199；不授权新平台录制、ASR推理、云上传或LLM调用。现有LLM未知记录不重放。旧失败/媒体保留。

ARC工作副本 .worktrees/LIVE-029-integration，负责ASR providers契约/必要重试契约、OpenAPI、目录门禁、文档与串行集成部署；BE .worktrees/LIVE-029-backend负责capture及必要materials导入函数与测试；FE .worktrees/LIVE-029-frontend负责既有组件和合成浏览器测试；QA非作者固定SHA独立审查。运行证据runtime/live-029。允许范围见scripts/checks/repository.py的LIVE-029，跨范围先统筹登记。

材料卡选择local/tencent，显式保存工作区默认偏好，云处理隐私授权与单次请求/金额声明分开。GET /api/v1/asr/providers返回providers数组：provider、configured、reason、max_duration_seconds、max_audio_bytes、network_checked:false。仅本机配置检查，不调用供应商/推理；configured非连接验收。腾讯现base64 WAV 5,000,000bytes，保守156秒；local按media配置和14400秒上限，不代表长音频质量已验收。未知时长/超限云材料前端拒绝并解释，后端原始格式/大小验证仍权威。聊天模型配置不作为ASR凭据。

历史采集默认折叠，当前/最新紧凑，材料提前展示；复用cursor分页，不删除旧记录。进行中停止入口保持可达。

StartInput增加可选duration_seconds/max_bytes；每run冻结recording_limits，health公布预设30m/1h/2h/4h、默认2h/8GiB、服务端max4h/16GiB、可用磁盘限制、普通上传上限。单fragmented MP4，无跨文件恢复承诺；原run未快照显示null。停止阈值允许有界封装尾部余量，最终导入上限绑定run批准快照，不能放宽普通上传512MiB。磁盘按源/上传/最终副本峰值三份及2GiB保留核算，同盘与不同盘分别检查；录制循环和收尾/导入hash、copy、ffprobe覆盖心跳、取消、upload lease。不通过增加lease掩盖阻塞。

验收以runtime/live-029/pm-acceptance.md和qa-plan.md为基础：定向原生PG独立UUID库、合成媒体超过60秒、停止/磁盘/边界/取消与限额快照、权限和隐私、真实5199页面展开/配置/刷新。不新做真实平台长录或云测试，不称2h真实稳定性通过。独立Review绑定最终head，适用CI通过再空闲部署；保全旧ASR失败/原片与秘密配置。腾讯未配置需明确提示，长云分片及断点恢复为后续范围。
