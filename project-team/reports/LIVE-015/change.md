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

capture_helper为本机API命令行入口，不是前端页面；无后台常驻或任务自动唤醒承诺。API8197/PG15490当前保留以供验收，接收8198只在显式任务运行时占用。私有账号/会话引用在runtime/live-015/preview-account.json（0600），不在Git/报告展示密码。

## 回滚

未集成main前保留本分支/运行证据即可；无需改主仓库。集成后回滚应由ARC串行撤回接线与模块，先停止本轮任务，保留runtime源文件；数据库0006仅新增capture_runs，降级会删除采集元数据，不能在有需要保留的运行记录时盲目降级。旧材料/ASR/任务表和已有迁移均未重写。
