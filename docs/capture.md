# 统一直播采集（LIVE-015～017）

产品默认关闭；2026-10-07本地联调已由用户授权开放抖音HTTPS限定60秒/50MB手动试录，当前8199 API与5199前端提供此入口。视频号未开放，8197与DLNA接收端保持停止。Cookie已支持工作区设置；真实解析成功不等于媒体录制验收。LIVE-025曾因返回HTTP候选被策略拒绝；LIVE-026补齐受限HTTPS候选适配后，已完成一个授权房间的一次约60秒录制、导入与Edge播放，详见reports/LIVE-026/delivery.md。该结果不等于所有房间或长期录制验收。精确版本与独立证据见[技术审查](../project-team/reports/LIVE-015/arc-review.md)。

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

上游完整代码只放 runtime，不复制进业务层。DLR bridge 阻止上游自动安装 Node 和日志初始化；以验证 TLS、禁代理环境/重定向、固定 `live.douyin.com` 的 HTTP 请求替换上游默认 `verify=False` 网络调用；取流 URL 的 HEAD 探测延后至受控 relay。上游缺少 status 的异常返回明确记解析失败，不按其默认值冒充未开播。工作区 Cookie 从私密设置读取，经子进程 stdin 传给解析桥；工作区请求及执行器不回退环境变量，也不使用上游内置示例 Cookie。低层适配器单独使用时的旧环境变量兼容不用于产品工作区流程。

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

## LIVE-020 浏览器任务执行与恢复（待独立验收）

运行参数仍分层YAML，默认enabled=false、execution_mode=operator。本机需要明确设置execution_mode=native，由环境所有者启动一个独立进程：

```sh
python -m live_review.workers.capture_executor
```

它消费现有数据库Outbox里的capture_v1并调用既有run_job，无新队列或任务表。HTTP请求只持久创建任务；浏览器无需每个job另开终端。当前容量为一条采集串行执行，后续任务保持queued。原生执行器仅消费capture，不执行手动提交的ASR；ASR消费仍需既有媒体worker，由统筹部署。本轮运行资源由ARC登记API8199/UI5199/PG15500/DLNA8200/runtime/live-020，启动状态以实时health和验收记录为准。

GET /api/v1/capture/health新增execution：mode、automatic_dispatch、ready、state、reason、heartbeat_at。原生执行器就绪同时要求受控root锁仍被进程持有、10秒内心跳、数据库/策略指纹一致和数据库可连接；不以残留心跳文件冒充服务在线。state为disabled/manual/unavailable/idle/busy/draining；busy允许排队，draining禁止接收新任务。新run在native未就绪时返回503 capture_executor_unavailable，既有幂等请求仍返回相同run。进程与API必须在同主机/同runtime目录，此就绪机制不适用于跨主机服务。

GET /api/v1/capture/runs?session_id=UUID&limit=20&cursor=opaque恢复当前工作区场次的采集列表，返回items,next_cursor。limit范围1..100；以created_at/id倒序分页；每个run额外返回created_at。前端刷新后用服务端run恢复显示；提交结果未知时复用同幂等键，不创建另一条录制。

SIGTERM/SIGINT令原生执行器进入draining、停止消费、对当前任务请求受控停止，等待既有FFmpeg/接收助手退出和关闭后导入；不把收到退出信号当成文件已关闭。SIGKILL继承原handler父进程管道watchdog与Job租约恢复。恢复仍要求closed manifest，只有started标记不自动重录或导入未关闭片段。

HLS支持边界沿用严格解析器；普通本地音视频全链功能测试和纯解析拒绝测试不能替代尚未完成的端到端出站隔离复核。不重跑被平台安全审核中止的探针，不通过更换工具规避。真实平台启用仍须最终就绪审查与PM集中安排直播间/手机样本。


## LIVE-023 平台就绪与限定试录

health.providers每个平台提供start_ready、source_access_configured、blockers(code/message)，仍保留dependencies_ready与real_platform_verified=false。start_ready只证明配置、执行器和媒体工具满足启动条件，不证明任何真实直播已录制成功。空/无效stream_domains、缺解析组件、未开放平台、执行器离线和缺媒体工具分别给出中文原因。native新建API采用同一门禁；既有幂等请求优先恢复原run。allowed_platforms默认两平台兼容，显式受限时probe与operator/native新建均不能越过；停止/导入不受新建平台门禁影响。

health.limits返回max_seconds/max_bytes，页面显示试录上限。https_only默认为false以保留已有配置；本机短试录将显式设true、allowed_platforms=[douyin]、stream_domains=[douyincdn.com]、60秒/50000000字节。仅允许该域及子域，视频号暂不开放；平台解析返回其他域或HTTP时明确拒绝，不能自动扩大范围或降级。配置变更先确认无活跃采集，drain旧executor，API/executor使用相同策略指纹再启动。

DNS在独立可回收子进程执行，每次最多5秒并受录制总deadline约束；初始解析等待消费停止检查，录制总计时在Relay创建之前开始。重定向和HLS子资源同样执行域/IP/HTTPS规则及解析期限。停止/超时先回收解析子进程；未确认回收明确失败，不伪造媒体已关闭。60秒是录制预算（含初始媒体DNS），不包含之前有独立超时的房间解析及之后的停止封装/导入时间。

独立静态审查与离线/本地合成回归只能支持用户自有或授权已知来源的限定短试录，不替代动态出站隔离、任意不可信媒体安全、真实平台成功或长期稳定性验收。尚无具体真实直播链接时，不发起试录。


## 工作区平台接入设置（LIVE-025）

入口：设置 → 平台接入 → 抖音。管理员将自己的浏览器 Cookie 值粘入密码输入框；保存后清空，刷新不回显。GET/PUT/DELETE `/api/v1/capture/settings/douyin` 读/存/清除；POST 同路径 `/check` 只执行一次有界解析，禁止自动录制。写操作需要当前管理员、可信Origin、CSRF及expected_revision；重复检查和版本冲突明确返回409。更新/清除与检查并行时，旧检查不能覆盖新版本。

工作区设置存储在 `storage_root.parent/private/capture/<workspace_uuid>/douyin.json`，目录0700、文件0600，拒绝符号链接/异常属主/宽松权限，原子替换并fsync。这个路径不属于材料下载对象命名空间。它是操作系统权限保护的明文，不是加密保险库；部署备份必须按凭据管理，不能提交Git或打入交付包。响应、异常、任务参数和日志均不含Cookie或临时签名URL。

未保存=not_configured；保存后=unverified；检查返回有效未开播状态，或开播且明确选中的URL满足静态协议/域策略时=verified。HTTP401/403归needs_update，含义为需要核对访问条件，不足以证明Cookie过期；空响应、限流、网络、结构或源策略错误归check_failed。服务就绪单独显示，状态不互相代替；历史检查仅对应记录的房间与时间，不能保证另一房间/下一次请求。检查不验证CDN连接、重定向、HLS子资源或实际可录制性，这些仍由录制阶段逐跳验证。

Cookie在执行器开始解析时读取一次不可变快照；更新/清除对后续检查和未开始解析的排队任务生效。已开始解析/录制的任务保持旧快照直到结束；需要立即终止时在场次页停止任务。清除后工作区传空Cookie，绝不回落服务器全局env或上游示例。

选流遵循固定DLR的非h265优先FLV规则，再考虑其明确返回的HLS/record候选，同时服从当前HTTPS与域策略。LIVE-026在没有合格原始HTTPS地址时补充协议候选：仅对同时命中配置白名单与douyincdn.com边界的HTTP默认端口地址，构造同主机、同path/query的HTTPS候选（显式80改为默认443）。优先使用原始合格HTTPS，再按非h265的FLV/HLS偏好选择转换候选；不转换任意域/端口，不发送Cookie给CDN，不回退HTTP。候选转换并不证明CDN可用，证书和每一跳仍由录制relay检查。全部候选不合格时在解析/检查阶段返回https_required/domain_not_allowed/unsafe_stream_url，不进入录制。TLS、域限制、重定向和HLS逐资源检查不放宽。

LIVE-026依据固定上游main.py1150–1151的HTTPS转换选项补齐协议层；上游该选项默认否，默认允许HTTP，本系统仍要求HTTPS。settings检查仅解析/静态策略，不是网络媒体验收；真实录制结果见本轮报告。
