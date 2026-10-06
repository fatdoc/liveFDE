# LIVE-015～017 统一采集接入本地变更单

作者 CAP-01，任务 `01a11105-8328-7283-b726-8e9d34e75c36`。产品基线 `61c2cbbf6f74f20d752374a96bda09abba0209ed`；已取 ARC 登记提交209fc61，对应本分支154e2cd。无 remote，无 PR、合并、发布或客户验收声明。独立 Review 尚待 ARC 安排固定提交审查，作者不自批。

## 结果与范围

统一 CaptureRegistry、抖音解析适配、视频号本地 DLNA 助手、内存受控 URL relay、FFmpeg 录制与原子 manifest、CaptureRun 状态/API、既有 jobs 两阶段、材料导入及场次关联、手动 ASR 入口。没有另建 Demo 或任务系统；不含评论、订单、评分、报告、前端采集页面。工作副本 `.worktrees/LIVE-015-capture`；所有本轮运行产物 `runtime/live-015`。源文件始终保留，无自动清理；旧CPB/5196/8196/15480未改。

抖音首版限定PC数字房间URL，不支持短链/主页。视频号限定DLNA，未宣称AirPlay加密音频或完整手机流程已验。媒体开始/停止/中断真相独立于导入与ASR；录制达到60秒/50MB/8GiB reserve任一阈值停止并记录非整场完整状态。

实现入口/安装命令/API示例/手机操作/恢复边界见 `docs/capture.md`。上游固定commit、许可、源码封装差异与问题来源亦见该文档；许可证原文和实际依赖清单在本报告目录。DLR add187f8/4.0.7 MIT；finder 07271ab/0.4.3 GPL-3.0-or-later，不以子进程宣称无GPL义务。产品依赖锁未修改；两个上游只在runtime独立环境安装。

## 验证证据（提交前）

- 22项新增capture专项：全部通过，零skip；证据 `runtime/live-015/evidence/live015_suite_45e913e4f91d49c5872b7b50eab8671c/{pytest.xml,pytest.log,tmp/}`。包括两租户鉴权、非法来源、重复开始、未开播/解析失败区分、等待投屏/收到URL/实际录制状态、真实FFmpeg主动停止与全文件解码、磁盘前置/中途不足、进程崩溃、时长和体积阈值、停滞、地址403、重启标记保护、重复导入、finalize已提交后故障重入、场次关联、手动ASR排队不执行模型、运行中stop/cancel与接收进程退出。
- 原有313 + 新增21 = 334项后端完整回归，零失败/错误/skip；证据 `runtime/live-015/evidence/live015_suite_fa825646540349749bbef7290d0bdbbd/`。其后新增的一个完整视频号状态链测试已在上条22项专项中通过；最终复核由独立QA绑定提交执行。
- 首轮完整回归331通过/1失败：`runtime/live-015/evidence/live015_suite_cdc48ff5dffd46d68c5c2ecb0a412393/`。隔离PG初始TimeZone=Asia/Shanghai导致既有material上传expires_at同一时刻UTC与+08字符串比较失败。新测试库UTC已固化于live015_acceptance.py；live015环境UTC由live015_environment.py --configure-db固化，不改旧业务测试去掩盖失败。
- 新代码Ruff、compileall通过；0006_capture唯一head，down_revision=0005_asr_settings；PG实际live015/live015/UTC/15490。新的环境私有文件/FIFO/越界端口等与scope单测共8项通过。
- 原工程36守卫在app主目录只读执行通过。直接在capture worktree跑旧脚本得到22通过/14拒绝，原因旧006/006B环境脚本硬编码只允许app路径；此项未算作capture分支全守卫通过，也未修改旧脚本。新模块专项/迁移/scope分别验证。
- 实际上游 finder CLI 在8198提供device.xml，并对合成SetAVTransportURI返回200和正确URL；`runtime/live-015/evidence/helper-smoke.json`。这是实际上游协议，不是真实手机/真实平台/录制证据。
- 实际DLR固定源码在独立venv导入通过（0次平台调用）；未提供Cookie。API实际健康证据 `runtime/live-015/evidence/preview-health.json`。
- API8197 → 本机helper → 真实finder等待投屏 → API stop → 两阶段退出：run `4563f820-4f54-4023-8eab-a2d0efa3d404`，job `4c3e9386-2a0e-4aa4-8b64-d72b84436e01`，最终stopped，manifest/material为空，不能称录制成功。

### 合成实际录制产物

`runtime/live-015/evidence/live015_suite_45e913e4f91d49c5872b7b50eab8671c/tmp/test_actual_av_active_stop_and0/capture/recording.mp4` 与同目录 `manifest.json`。这是FFmpeg从本地合成音画HTTP流录制、主动停止、FFprobe音视频/时长验证并完整解码通过的实物，不是抖音/视频号直播素材。故障测试里的替代进程生成文件单独标synthetic process fault，不能替代真实FFmpeg证据。

## 未验证与已知限制

真实平台录制0、真实手机投屏0、本轮ASR模型调用0（仅真实材料到既有ASR任务API排队）。未使用腾讯凭证或付费模型。真实平台需要PM集中获取有权录制的抖音PC房间与同LAN手机操作；未找到可用直播/投屏时不阻塞已具备条件的功能。

没有原生低延迟ASR、多人长录音质量或跨片说话人一致性声明。上游风控/取流签名/CDN域可能变化；未验证私有/会员/DRM直播。完整生产broker部署、实际手机兼容、长直播稳定性未验证。单片500MB共享默认/本机50MB，超过既有上传限制保留待导入；已有上传TTL过期需运维处理，不绕过旧校验。进程崩溃无closed manifest不自动修复/导入partial，也不偷偷续录；重新开始新run或后续明确恢复工具处理。

capture_helper为本机API命令行入口，不是前端页面；无后台常驻或任务自动唤醒承诺。API8197在安全修复期间主动停止；PG15490保留以供验收，接收8198只在显式任务运行时占用。私有账号/会话引用在runtime/live-015/preview-account.json（0600），不在Git/报告展示密码。

## 回滚

未集成main前保留本分支/运行证据即可；无需改主仓库。集成后回滚应由ARC串行撤回接线与模块，先停止本轮任务，保留runtime源文件；数据库0006仅新增capture_runs，降级会删除采集元数据，不能在有需要保留的运行记录时盲目降级。旧材料/ASR/任务表和已有迁移均未重写。

## 首轮独立审查阻断与修复

独立QA审查a1702c0后确认：① HLS未加引号URI属性未被重写，存在目的地址校验绕过；② 普通TS分片转成.media后FFmpeg拒绝（独立正常HLS探针direct=0/relay=183）；③ duration替代进程测试依赖Python在1秒内启动，独立专项22项有1失败。原证据在runtime/live-015/qa/，保留不覆盖。ARC另指出执行期actor与工作区复验不足、CaptureError导入失败未持久展示，已一起修复。

修复：新增HLS标签/属性严格解析与URI统一重写（未知/不合规fail-closed），安全后缀映射，真实正常HLS合成AV回归；HLS实测又发现碎片MP4直接复制ADTS AAC时截短，改为视频copy/音频AAC128k。共同execution_actor覆盖worker录制/心跳和worker/API导入；Import持久化所有受控错误；manifest严格验证。故障测试在替代进程launch返回前同步放置合成媒体，避免解释器冷启动与1秒录制限时竞争，不扩大生产max_seconds。

37项修复专项0fail/0skip：runtime/live-015/evidence/live015_suite_751d892dfba94ec68be0b23500f38501/。正常HLS实际音视频产物位于其tmp/test_actual_hls_ts_relay_recor0/recorded-hls/，与早前MP4直流测试分开。后续完整351项通过（0失败/错误/skip），证据runtime/live-015/evidence/live015_suite_1f23603199d843edbb1eb4e01f2889c0/；其tmp/test_actual_hls_ts_relay_recor0与recor1/recorded-hls分别为普通和AES-128合成HLS实物，均2220ms、音视频齐全且完整解码通过。

ARC预审追加：已导入材料后owner失效导致手动重试或worker阶段重试降级状态。两入口共用material_id优先保留状态规则，仍拒绝失效actor并持久记录诊断；补完整导入后的撤权、其他管理员重试、导入提交后stage回写丢失模拟断言。

审查边界：原QA安全探针后续被平台自动安全审核中止（possible cybersecurity risk），未获得该轮完整批准。本轮不重复被拦截探针，采用纯解析层拒绝断言与普通本地HLS播放检验防御修复；后续由非实现作者ARC审查固定修复SHA及普通功能验收，不宣称已完成全量安全测试。未向用户发起额外授权要求，真实平台试录暂缓直到技术复核完成。

最终追加状态修复后的39项capture专项全部通过（0失败/错误/skip）：runtime/live-015/evidence/live015_suite_f7765c45af814ec490788b81a3239ea7/。包括API与worker已导入后撤权重试；Ruff、diff检查和LIVE-015范围检查0违规。
