# LIVE-027 真实直播材料本地ASR与时间戳

用户经PM明确授权一次现有真实材料本地ASR及时间戳验收。基线92014117dcb7ef96e457e82d9b83cd8c637dfc1f；ARC执行owner；feat/LIVE-027-asr-acceptance/.worktrees/LIVE-027-asr-acceptance；runtime/live-027。原material41507f74-c477-4744-be5a-558ff0496480/run3407c23d，60.067秒，不重传、不重录、不云调用、不下载模型；未知结果不重放。

先核DB/worker空闲与旧execution_stop_unconfirmed明确停止ACK。核source=local/synthetic=false、全文与分段、起止边界/单调性、timestamp_source；采集complete=false与ASR.complete分开。真实听核能力不具备时明确未验，不能用另一模型输出代替听核准确率。

FE负责独立.worktrees/LIVE-027-frontend，仅MaterialTranscription.tsx/LiveSessionDetail.tsx、按需transcriptionTimeline.ts与登记tests：当前材料页显示起止/VAD来源，点击定位同一材料播放器，不重建UI不改ASR提交机制；未知/无效时间不得定位。ARC持任务/门禁/报告/运行/串行集成；QA固定SHA非作者Review及结果独立复核。共享依赖/后端/API不在本轮写范围，必要修复先内部协调。

## 诊断范围补充
PM于2026-10-07批准最小安全错误码传递/日志修复。提交前发现材料已有失败job974e38db-d7e6-4717-820c-f2cc6747a744，未新增模型调用；原错误证据保留。BE仅负责handler_process.py/job_runner.py、local_worker/protocol.py/server.py及test_asr_error_reporting.py/test_local_asr_worker.py：固定白名单错误码跨进程保留，不记录文本、音频、凭证或原始SDK错误，不改变停止确认/unknown分类/重试规则。注册后独立BE工作副本，QA固定SHA。暂不重试真实模型；前端真实时间戳与听核未验。
