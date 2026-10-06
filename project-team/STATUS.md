# 当前事实与任务
更新：2026-10-06，非自动监控。
已有 React Demo、CPB 审计、规范、Python工程基础和业务契约草案。LIVE-004身份/场次/材料已验；LIVE-006C的ASR设置/试用已接真实后端，真实本地文件与窗口流转写闭环已验。其余页面仍Demo；报告、评分未实现。LIVE-015～017采集基础代码完成有限技术验收并集成，默认关闭，真实平台接入待验收。
Git：app/.git，main 已有首次基线 13665739fb29d8aa70a9e78d32bce3d58c81bd0f；无 remote。前端 frontend/web，旧 CPB 已归档；独立技术/浏览器验收通过，试验 worktree 已验证并移除。

| 任务 | owner | 状态 | 依赖 |
|---|---|---|---|
| LIVE-001 | ENG-01 | done | 技术验收和 PM 最终核对通过；代码基线1366573，详见reports/LIVE-001/qa.md |
| LIVE-002 | ENG-01 | done | 独立审查18e721f和PM核对通过，集成19fede3；PG/原生MQ真实验证 |
| LIVE-003 | ARC-01 | done | 独立审查 b7d4efa、PM核对通过，集成26aaf4a；17正例/15负例 |
| LIVE-004 | ARC/BE | done | 独立Review和PM最终验收通过；集成a9a15d2；32真实测试/0skip，详见reports/LIVE-004 |
| LIVE-005 | BE-01 | done | 集成8a34b5f；独立QA及PM最终验收通过；52真实测试无skip、11故障场景、20工程守卫 |
| LIVE-006 | AI/CFG/BE/ARC | done | 集成649eb07；独立QA与PM最终验收通过；126后端测试0skip、28工程检查；0真实模型调用 |
| LIVE-006B | CFG/BE/ARC | done | 集成706f28e；独立组合QA及PM最终验收通过；204后端tests零跳过、36工程checks及v1/v2烟测；真实调用0 |
| LIVE-006C | LOCAL/TENCENT/UI/ARC | done | 代码751c331；独立QA及PM按基础版范围通过；313后端0skip、36工程、真实本地2file/WS及页面上传；腾讯真实调用和质量缺口见报告 |
| LIVE-007～014 | 见计划 | backlog | docs/05 |
| LIVE-015 | CAP-01 | in_progress | 基础代码已集成且默认关闭；e78014b独立352项通过；真实抖音及出站隔离复核待验 |
| LIVE-016 | CAP-01 | in_progress | 本机DLNA接入基础已集成，接收端停止；真实手机/视频号待验 |
| LIVE-017 | CAP-01 | in_progress | 导入/去重/场次关联及手动ASR入口经合成媒体验证；真实平台到ASR闭环待验，非done |

待决策：远程组织/仓库/可见性；评分标准；后续多场景标注样本、真实云配置与预算。已授权的本轮公开本地样本实测完成，不等于新增云调用授权。
版本/端口/DB 隔离由 LIVE-002 探针登记；不抢占已有预览。

交付限制：无remote/远程CI；RabbitMQ容器模式尚未实跑（原生独立4.2.3已验）。发布前须补Compose全栈验证，见LIVE-002/follow-up.md。8188仅烟测，结束关闭；Demo5188保留。

LIVE-004环境：PG15440保留；8194仅烟测已退出。原5188 Demo仍未接后端。原LIVE-002 PG15432保留，未用于本轮业务迁移。各QA迁移基线分库，未清空/降级已有库。

LIVE-005结束：PG15450与MQ5675保留数据及运行环境；API8195和本轮worker/handler均退出，开发副本保留审计。前端仍Demo；随后用户经PM另行授权LIVE-006（见本轮记录）。

LIVE-006结束：代码649eb0759d1adf397e24f09b9ba458e612989939，独立批准树a994b27d04d219301d27ac674f909f09b1ee56d2。PG15460/live006和本轮独立回归库/运行实物保留；所有烟测worker/FFmpeg已退出，各岗位写锁与QA数据库锁已交还。纯文档提交后释放main index锁；LIVE-007及后续仍backlog，不自动启动。前端仍Demo，真实供应商调用须另行确认配置与预算。

LIVE-006B结束：代码706f28ef87333718d5ce34c2ddf634fedf11a6f3，独立批准树e8d9d5f9289b307c65d243b61d5892c17fbfb8f8。PG15470与本轮独立库/产物保留，CFG/JOBS副本干净只读保留，QA数据库锁已交还；无本轮worker/FFmpeg常驻。ARC纯文档收尾提交后释放main index本轮独占。不启动007，不新增真实模型授权；前端仍Demo，非ASR仅声明。

LIVE-006C结束：最终代码751c331e834823021db6ba85bda410e5bd1fd04a，独立批准树b1f19ae8f4b3117545b22d841c8a34abf6c2c6d3。PM验收本地ASR基础闭环与设置，非十场景质量全部达标。真实腾讯/多人/方言/长录音/DER/情绪准确率未验，云长文件、MPS、原生低延迟流仍缺；首次revision0 GUI未测但API/源码门禁已验。预览5196、API8196、独立worker和PG15480保留，worker空闲60秒卸载模型；不伪称自动开发/监控。旧环境不动，员工副本保留审计；main收尾仅文档。入口、账号获取方式、91文件清单、实测/失败保留与恢复见reports/LIVE-006C/change.md。不启动LIVE-007。

2026-10-06用户另行在CAP任务直接授权提前LIVE-015～017，不等待M3/M4；不改变007～014 backlog。开发基线61c2cbb，feat/LIVE-015-capture，.worktrees/LIVE-015-capture，runtime/live-015。API8197/助手8198/PG15490拟保留，登记时无TCP监听（不等于已启动），live015独立新库。共享接线/依赖/唯一0006迁移由CAP在其副本独占，ARC只维护台账/门禁与串行集成。原预览不动；独立Review待首个可审SHA再启动，当前不声明通过。详见tasks/LIVE-015.md。
