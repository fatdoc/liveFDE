# 统一直播采集（LIVE-015～017）

当前仅批准**默认关闭的基础代码集成**，不是抖音/视频号产品验收完成。真实平台、手机投屏、本轮真实ASR及端到端出站隔离安全复核待完成；API8197与DLNA接收端保持停止。下文为实现说明和后续操作参考，暂不执行真实来源试录。精确版本与独立证据见[技术审查](../project-team/reports/LIVE-015/arc-review.md)。

实现位于唯一后端，不新增独立业务 Demo、队列或模型系统。当前首版支持抖音 **PC 数字直播间地址** `https://live.douyin.com/<room_id>`，不接受分享文案、短链、主页链接或签名取流地址。视频号为本机 DLNA 投屏接收，输入固定 `phone_cast`。真实平台验收状态见本轮报告，安装成功、协议测试、真实平台录制和真实 ASR 分别记录。

## 链路与状态

`POST capture/runs` → CaptureRun + 既有 Job/两阶段 + outbox 同事务 → 既有 dispatcher/Celery/handler 子进程 → CaptureRegistry → 适配器获得短期 URL → 内存 URL relay → FFmpeg → 关闭媒体与原子 manifest → 既有 upload/receive/finalize/场次关联 → 手动 ASR。

主要入口：`modules/capture`（鉴权业务、状态、导入）；`integrations/capture`（策略、上游适配、受控媒体）；`workers/capture_jobs.py`（既有执行器适配）；`workers/capture_operator.py`（本机按 job_id 执行已有任务）。API 不启动录制后台线程；录制与 HTTP 请求生命周期分离。生产继续使用已有 outbox dispatcher 和 Celery。本机 operator 是现有 runner 的命令行入口，不是另一套任务系统。

状态：`queued → probing`（抖音）或 `waiting_for_cast`（视频号）→ `url_received → recording → recorded → imported`；另有 `stopped / failed / canceled`。只有实际 FFmpeg 媒体进度才进入 recording，收到 URL 不能作为成功录制。API stop 返回的是 `stop_requested=true`，不是文件关闭证明。stop 等待接收/录制退出；cancel 沿用 `/api/v1/jobs/{job_id}/cancel`，进程组确认终止后任务 canceled，不自动导入取消中的文件。

`job_status=succeeded` 仅表示这次 record/import 阶段执行完成。`manifest.complete` 描述所录区间是否受控结束，不代表覆盖整场直播；主动停止为 true，抖音重新探测确认下播为 true；断流、未知 EOF、地址过期、进程崩溃、时长/体积/磁盘上限为 false，记录 end_reason。视频号 URL 结束无法可靠反推手机直播状态，因此 EOF 保持 source_eof_unconfirmed。可播放的中断片段在进程已关闭后可以导入，状态同时显示已录制/已导入；异常不会伪装为整场完整。

当前每次采集一个片段 `segment_index=0`，不做自动断流续录或跨片拼接；没有跨片说话人身份合并。抖音解析最多 2 次（可配 1～3），指数退避；地址失效不无限复用旧 URL。重新开始是新的 capture_run_id 和真实时间区间。

## 上游固定来源与封装

| 上游 | 固定版本 | 声明许可 | 使用范围 |
|---|---|---|---|
| [DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder/tree/add187f8d8c7ff7d231fcbee45cbb4f1ed247d3a) | commit `add187f8d8c7ff7d231fcbee45cbb4f1ed247d3a`，pyproject 4.0.7 | MIT | 独立 venv/进程调用 `src/spider.py:get_douyin_web_stream_data` 与 `src/stream.py:get_douyin_stream_url`；不导入其主循环/任务/录制器 |
| [wechat-finder-dlna](https://github.com/gtoxlili/wechat-finder-dlna/tree/07271abdb5707cf8074483a33c2519b457ccc669) | commit `07271abdb5707cf8074483a33c2519b457ccc669`，0.4.3 | pyproject `GPL-3.0-or-later`，README 简写 GPL-3.0 | 单独安装原始 CLI，仅 `--protocol dlna` 接收 URL，私有 stdout 管道；不调用其 `--record` |

上游完整代码只放 runtime，不复制进业务层。DLR bridge 阻止上游自动安装 Node 和日志初始化；以验证 TLS、禁代理环境/重定向、固定 `live.douyin.com` 的 HTTP 请求替换上游默认 `verify=False` 网络调用；取流 URL 的 HEAD 探测延后至受控 relay。上游缺少 status 的异常返回明确记解析失败，不按其默认值冒充未开播。自有 Cookie 仅通过指定环境变量输入子进程 stdin；不使用上游内置示例 Cookie 作为用户凭证。

Finder 支持的 AirPlay/Chromecast/加密音频功能没有全部接入本版。尤其 AirPlay 音频文件不等于完整视频；本版必须 FFprobe 同时检出视频和音频才可交付。手机与电脑同一局域网、允许 SSDP 组播；AP/访客网络隔离会导致找不到接收设备。接收端仅适用于可信局域网，不能暴露公网；上游 DLNA 服务不是有账户认证的云端采集服务。

许可证原文和实际依赖版本保存在 `project-team/reports/LIVE-015/`。独立进程封装不等于免除 GPL 的分发义务；当前只做本机开发验证，未发布/再分发包。后续打包需要同时保留固定上游源码、许可、安装脚本和修改说明，不能统一标 MIT。

阅读的当前问题来源：[抖音断流与丢帧反馈 #1028](https://github.com/ihmily/DouyinLiveRecorder/issues/1028)、[链接/录制异常 #1246](https://github.com/ihmily/DouyinLiveRecorder/issues/1246)、[抖音当前问题列表](https://github.com/ihmily/DouyinLiveRecorder/issues)、[视频号问题列表](https://github.com/gtoxlili/wechat-finder-dlna/issues)。这些反馈提示风控/格式/断流风险，不是本机实际可用性证明；视频号公开列表检查未获得可直接复现本版手机故障的详细 issue 证据。

## 配置与安装

沿用 `LIVE_MODEL_CONFIG_DIR`、安全 YAML 读取与 deep_merge，单独加载 `capture-policy.yaml` → `environments/<environment>.capture.yaml` → 开发/测试 `capture.local.yaml`，不改变旧模型配置快照。模板 `config/capture-policy.example.yaml` 默认关闭。Cookie/Token 不写 YAML，默认环境变量 `LIVE_CAPTURE_DOUYIN_COOKIE`；API 不接受凭证、任意磁盘路径或执行命令。

本机已登记：API 8197，DLNA 8198/UDP SSDP 1900，PG 15490/live015，运行目录工作区 `runtime/live-015`。动态内存 relay 只绑定 127.0.0.1 随机空闲端口，URL 凭证不出进程。旧 5196/8196/15480 不改。`private.env` 权限 0600；路径、依赖解释器和目录在私有 `config/capture.local.yaml`。本机真实试录限制为 60 秒、50,000,000 字节、最低 8 GiB 空闲。阈值都在录制前/录制中检查；到阈值会受控停止并保留中断原因，不删除用户文件。FFmpeg `-fs` 是停止阈值而非精确字节配额（可能超过一个封装包），磁盘保留量须覆盖此余量与导入的两份临时副本。

从工作区执行部署准备（实际源已固定在下列路径，已存在时不要重复 clone）：

```sh
uv venv --python 3.11 runtime/live-015/douyin-venv
uv pip install --python runtime/live-015/douyin-venv/bin/python -r runtime/live-015/upstream/DouyinLiveRecorder/requirements.txt
uv venv --python 3.11 runtime/live-015/finder-venv
uv pip install --python runtime/live-015/finder-venv/bin/python ./runtime/live-015/upstream/wechat-finder-dlna
```

产品后端不新增依赖，不改 uv.lock。上游依赖独立安装后的精确版本见 `upstream-dependencies.json`；上游要求范围不是永久兼容承诺。升级上游必须更改固定版本、重新审查接口和复测，不自动拉最新。

在开发副本根执行，环境包装器只读取本轮 runtime/private.env：

```sh
uv sync --frozen --project services/backend
services/backend/.venv/bin/python scripts/checks/live015_environment.py .venv/bin/python -m alembic upgrade head
services/backend/.venv/bin/python scripts/checks/live015_environment.py .venv/bin/python -m uvicorn live_review.main:app --host 127.0.0.1 --port 8197
# 已由API创建job后，在另一终端运行已有任务（手机与本机在同一LAN）：
services/backend/.venv/bin/python scripts/checks/live015_environment.py .venv/bin/python -m live_review.workers.capture_operator <job_id>
```

生产使用既有 `workers.dispatcher --loop` 与 Celery 配置；本轮未新增/验证生产 broker 部署。本机 `/health/ready` 会因未配置 broker 显示 not_ready，这是 operator 模式边界，不冒充生产就绪。

## 接口与手机操作

所有接口沿用登录 cookie、工作区隔离；修改请求须 Origin 与 X-CSRF-Token。以下 JSON 为示例，不含凭证：

```text
GET /api/v1/capture/health
POST /api/v1/capture/probe
{"platform":"douyin","source_ref":"https://live.douyin.com/123456"}
POST /api/v1/capture/runs   （必需 Idempotency-Key）
{"platform":"douyin","source_ref":"https://live.douyin.com/123456","session_id":"<已建场次UUID>"}
POST /api/v1/capture/runs   （视频号）
{"platform":"wechat","source_ref":"phone_cast","session_id":"<已建场次UUID>"}
GET /api/v1/capture/runs/<capture_run_id>
POST /api/v1/capture/runs/<capture_run_id>/stop
POST /api/v1/capture/runs/<capture_run_id>/import （任务终态后重试已关闭文件导入）
```

1. 登录并建立主播/场次，创建采集 run，启动返回 job_id 的 operator（或已配置生产 worker）。
2. 抖音：输入受支持的 PC 直播间地址，开播检测/取流后自动开始，最长按本机限制录制。风控需要 Cookie 时在本机私有进程环境配置，不能把 Cookie 贴进任务消息。
3. 视频号：等待 API 显示 `waiting_for_cast`；手机打开有权录制的直播，菜单 → 投屏 → **FDE Capture**。没有投屏入口/找不到设备由真实手机验收记录，不能用抓取 URL 替代成功。
4. 看状态先 `url_received`，再真实 `recording`。主动停止调用 stop，轮询直到 recorded/imported 或明确 failed/stopped；不要把 202 当作已关闭。
5. imported 后返回 material_id；使用现有 `/api/v1/sessions/<id>/materials` 与受鉴权材料 content 播放。只有明确点击/调用 `/api/v1/asr/transcriptions` 才转写；需先保存 ASR 设置、提供 expected_revision，云端仍需本次授权与请求/金额预算。长文件超过现有 ASR 限制时仍保留已录制/已导入，不把采集改成失败。当前 API 的 transcription_status=not_requested 表示采集模块未请求ASR，不聚合后续用户独立创建的ASR任务。

## 故障与幂等

工作区+幂等键绑定请求哈希；同键同请求返回同一 run；活动来源部分唯一索引阻止重复开始。任务输入只有 run ID 与非敏感策略指纹，恢复时配置变化拒绝继续，避免换目录后偷偷再录。Record 有进程锁；视频号另有全本机 receiver 锁，避免两个租户抢同一个电视设备。已有 closed manifest 可恢复导入；只有 started 标记而无 manifest 的崩溃记录为 restart_interrupted，保留原文件、不自动重播未知直播区间。

关闭要求：FFmpeg 退出 → FFprobe 检查音视频/时长 → fsync + 媒体 rename → SHA256 → 原子 manifest。无关闭 manifest 的文件不能导入，文件大小稳定不是完成信号。manifest 保留平台、run、去敏来源、实际录制起止、媒体时长、hash/size、序号、完整或中断和原因。源文件在 API 确认前后均保留，本版没有自动保留期清理。

导入用 `capture:<run_id>:0` 固定上传幂等键，原采集 actor 固定，不能因另一个管理员重试而重复材料。复用 finalize 的持久 material_id；finalize 提交后、场次关联前崩溃可重复关联恢复，不只做 blob hash 去重。已有上传过期、文件过大等均保留录制产物并记录待导入；不绕过现有上传大小/格式校验。

取流仅 HTTP(S) 公网白名单域，逐次解析地址，拒绝私网/metadata/任意 file 等输入，连接固定到已检查 IP；重定向、HLS 子清单/密钥/片段都经过同一 relay。FFmpeg 仅允许 http/tcp/crypto 协议与 hls/flv/mpegts/mov 格式。新的真实 CDN 域必须由部署者审查后配置，不能由 API 调用方扩大范围。

## 测试

```sh
services/backend/.venv/bin/python scripts/checks/live015_acceptance.py
services/backend/.venv/bin/python scripts/checks/live015_acceptance.py --all
```

每次创建独立 live015_suite_<UUID> 数据库，日志/XML/合成媒体放 runtime/live-015/evidence；不迁移旧轮测试库。`--all` 覆盖后端回归（broker 专用测试独立于本机 operator 模式）。详细证据/失败修复/未验证项见 `project-team/reports/LIVE-015/change.md`。不宣称真实平台或ASR通过，除非报告里有独立的真实产物引用。

本机省去手动复制 job_id 的命令行入口（已安装环境与 API 启动后，在开发副本根执行）：

```sh
# 视频号：进入 waiting_for_cast 后，再在手机投屏列表选择 FDE Capture。
services/backend/.venv/bin/python scripts/checks/live015_environment.py .venv/bin/python -m live_review.workers.capture_helper --platform wechat --account-file /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-015/preview-account.json
# 抖音：将下面示例房间号替换为有权录制且正在直播的PC直播间。
services/backend/.venv/bin/python scripts/checks/live015_environment.py .venv/bin/python -m live_review.workers.capture_helper --platform douyin --source-ref https://live.douyin.com/123456 --account-file /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-015/preview-account.json
```

按 Ctrl-C 会通过鉴权 API 请求停止，再等待关闭和导入；等待最终状态再关闭终端。私有账号文件只在本机读取，不在命令行显示密码。正常部署可改用 `--username` 与 `--session-id`，密码交互输入；本机 preview-account 已建立两个合成验收场次，不是原 CPB 或客户账号。

本轮 PG 时间区固定 UTC：在启动 API 前执行 `services/backend/.venv/bin/python scripts/checks/live015_environment.py --configure-db`。验收脚本也会对每个新库固定 UTC。原因：原有材料幂等 API 的 expires_at 输出直接使用 DB datetime，PG 返回 +08:00 时会与首次 UTC 对象在字符串上不同（同一时间点）。本轮没有顺手改旧材料响应格式；保留首轮331通过/1时区失败日志，UTC配置后的完整回归另有证据。这是部署配置依赖，不是掩去失败。

关闭本轮 API 用其前台终端 Ctrl-C；当前 helper 每次运行结束关闭 DLNA 8198，未运行时无需单独守护进程。停止独立 PG（确认本轮测试/采集均已结束后）：`pg_ctl -D /Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-015/pgdata stop -m fast`。不对其它 PG、预览端口或模型worker执行清理。

## 首轮 Review 后的 HLS 与权限修复

HLS 现在先经过严格标签/属性解析，再交给 FFmpeg：URI 只能使用合规双引号字符串；重复键、未闭合字符串、未知属性、未知扩展标签、变量替换语法均拒绝。key/map/media/session-key/session-data/part/preload-hint/rendition-report/iframe 的 URI 统一受控重写，普通分片与 master 清单后继地址也受控。保留安全分片后缀，避免把 TS 全改为 `.media` 导致 FFmpeg 拒绝；未知 HLS 扩展会明确失败，不承诺所有直播清单变体都支持。

录制输出复制视频流、统一编码 AAC 128k 音频到碎片化 MP4。这样可正确处理 HLS TS 的 ADTS AAC，不再因直接复制 AAC 缺少配置头而只留下约0.3秒片段。普通 AES-128 HLS 用自生成合成密钥验证；这不代表支持付费/会员/DRM直播或视频号 AirPlay 的其它加密协议。

worker 开始采集、采集心跳和公共导入入口会重新检查 actor.active、actor/job/run/workspace 和场次归属。账号撤销或迁移后不得继续取流/导入，手动导入 API 同样覆盖。导入的 ApiError/CaptureError 均持久记录原因；hash/disk/manifest 问题不抹去已录制事实。manifest 使用严格结构、时区/时间顺序、音视频与哈希字段校验，拒绝异常文件类型/符号链接/过大文件；只有与run/platform/source匹配才可恢复。

已存在material_id时，手动重试/worker恢复遭遇撤权等失败仍保留imported状态和材料关联，错误单独展示；不会因后续鉴权失败把已导入事实降回recorded。
