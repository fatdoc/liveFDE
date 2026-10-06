# LIVE-006 媒体任务队列接线

沿用LIVE-005 Job/Stage/Outbox/Context，不建立第二套任务状态。注册名media.extract和media.asr；resolve只允许固定注册，不接受payload动态导入。抽音和转写共用已有material和workspace边界。

本模块分工：media_jobs负责材料核对/阶段；media_calls包装逐段调用意图与已知缓存；media_artifacts负责受控JSON产物；media_operator是本地操作员入口；media_configuration明确区分v1桥接与v2registry；integrations/asr/factory统一将已解析执行路由构造成适配器。未新增任意任务创建HTTP API。

## 操作员提交与执行

先按已有CLI创建管理员，按004上传流程得到session_media材料，再由受信任本地操作员执行。数据库迁移与LIVE_DATABASE_URL/LIVE_BROKER_URL/LIVE_STORAGE_ROOT从独立本轮env加载，不在命令参数中打印密码。

```sh
uv run --project services/backend python -m live_review.workers.media_operator submit \
  --workspace-id UUID --admin-id UUID --material-id UUID \
  --config /absolute/providers.offline.yaml --fixture /absolute/synthetic-transcript.json
uv run --project services/backend python -m live_review.workers.media_operator run-local \
  --workspace-id UUID --admin-id UUID --job-id UUID
```

submit输出单行JSON `{job_id,status,attempt}`；同事务写Job、Stage和Outbox，caller提交才生效。run-local经既有独立handler进程执行，stdout有生命周期日志，最后一行JSON为任务view；未成功退出1。也可由既有dispatcher/Celery消费同一个job；claim防重复执行。run-local不是第二个状态机。

真实ASR兼容链由provider profile和`--allow-network`本次授权双重门控制；默认无此参数，无法读取真实密钥或构建真实请求。仅本地操作员入口可写授权字段，不能由客户端任意指定。当前没有选定供应商、无真实模型验收；本轮只offline/MockTransport，后续使用必须先选兼容audio/transcriptions的服务、配置凭证与预算并获得实际调用授权。text/vision不在本任务执行范围。

fixture JSON格式 `{"segments":{"0":{"utterances":[{"text":"合成样例","start_ms":0,"end_ms":100}],"coverage":"full","missing_words":false,"no_speech":false}}}`；时间为段内毫秒，由媒体pipeline合并到全局源时间。fixture只允许development/test且结果synthetic=true，缺段/部分词/坏时间不伪装完整。

## 固定输入和阶段产物

提交和执行均核active admin/workspace/material；只接受同workspace session_media，读取Blob受控UUID键，固定原SHA/字节数并在实际抽音后再次比对。提交持久化无密钥provider snapshot、材料ID、source hash/size、storage fingerprint和每job授权标志。v1另存原YAML绝对路径；v2另存registry重载locator、显式/自动发现选项、model_id与可信runtime_environment。配置/存储漂移、管理员停用、材料改变均阻止执行。

提取和ASR产物位于storage/jobs/<workspace>/<job>/<lease-token>/，产物名随机UUID，JSON 600、目录700，引用相对storage根附SHA256/长度。先写完fsync再允许stage成功；结果数据库仅保留小引用/统计，不塞完整transcript。阶段间读取验证长度/hash；路径逃逸和符号链接拒绝。新lease用新目录，不覆盖历史产物。

ASR每段在provider调用前begin_paid_call，已知响应先存JSON再finish记录引用；已知错误也finish存安全错误码。重试相同job/chunk复用已知响应/错误，不增加调用次数；未知响应留intent并传播call_result_unknown，005禁止自动重放。所谓paid intent也用于合成fixture，用于验证机制，不能当作本轮实际付费证据。

整场预检请求段数/音频总时长；真实adapter另逐请求计数。相同job不会通过重试绕过已知/未知结果缓存。金额是配置声明而非实时账单硬cap。部分转写先落盘并记录stage.artifact.complete=false，然后阶段失败；extract成功产物在重试保留。不能把partial标记任务成功。

## 验证与限制

作者在独立PG15460/live006运行test_media_jobs.py：5项通过，真实FFmpeg抽取2.2秒合成WAV并切3段，子进程Job完整成功；partial保留且重试沿用3条已知调用；跨workspace/停用管理员/配置漂移拒绝；未知调用两次请求只触发一次provider；已知响应不重复调用。Ruff通过。完整004上传→场次→job的集成smoke及独立QA由ARC另行记录。

测试命令需显式LIVE_TEST_DATABASE_URL指向独立测试库，否则集成用例skip。产物由测试tmp_path保存；运行交付产物仍在runtime受控storage。不把本测试宣称真实ASR质量/供应商可用性、字幕业务表、复盘报告或前端接入完成。


## LIVE-006B：分层 registry 与旧任务兼容

新提交可使用 `--config-dir`，与旧 `--config` 互斥：

```sh
uv run --project services/backend python -m live_review.workers.media_operator submit \
  --workspace-id UUID --admin-id UUID --material-id UUID \
  --config-dir /absolute/app/config --model-id asr.default \
  --fixture /absolute/runtime/synthetic-transcript.json
```

`--model-id` 默认 `asr.default`，也允许显式具名ASR模型；其他capability不能进入本业务。fixture参数只有配置为offline_fixture的development/test环境才有效；仓库默认配置不等于模型已启用。真实ASR仍须本job的 `--allow-network`，不继承上一任务授权。本轮未真实调用任何服务。

配置分层加载和默认alias定义见 [model-registry.md](model-registry.md)。默认开发配置会自动读 `config_dir.parent/.env`，如 `app/config` 对应 `app/.env`，不需要shell source。只有登记AI密钥及白名单模型设置被使用，不更新os.environ，也不覆盖LIVE_DATABASE_URL/LIVE_BROKER_URL等运行Settings。CLI `--dotenv` 可指定私有密钥文件；`--local-config` 可指定开发local覆盖。文件权限和路径由CFG校验。

可信环境来自原有 `LIVE_ENVIRONMENT`，本任务不修改Settings环境定义。`--config-env dev/prod` 在边界先正规化为 `development/production`，再应用同一防降级规则；快照与locator只存canonical环境名。映射为：

| runtime Settings | 允许 `--config-env` | 适配器执行策略 |
|---|---|---|
| development | development（默认）、test | 开发/测试，可显式合成fixture |
| production | production（默认）、staging | 两者均生产限制，禁止fixture/local自动覆盖 |

例如 staging 应设置 `LIVE_ENVIRONMENT=production` 并传 `--config-env staging`；正式HTTPS origin等原有Settings条件仍须满足。production不能传development/test降低限制；development也不能仅改CLI参数冒充staging/production。正式环境不自动读取项目根.env，必要时通过显式 `--dotenv /absolute/private.env`，只解析AI设置。worker需使用提交时相同可信runtime环境，运行环境变化会拒绝旧v2任务。

v2把**最终完整merged公开配置**固定为snapshot_version=2，含所有登记模型/alias/参数/media与环境，执行和重试重载后比较完整hash；即便修改未选用LLM参数也会阻止旧任务继续。locator还固定实际使用的配置路径，显式/自动发现选择分开保存；不存在的可选local/.env不会被误当必需文件。模型API密钥只在授权时读取到内存，既不进job input/snapshot/产物，也不新增到worker Settings再传子进程。密钥轮换不改变公开hash，但新执行仍需有效凭证；未授权不会读取执行凭证。

旧 `--config /absolute/providers.yaml` 仍走原v1加载规则，不自动读项目根.env，不接收registry model-id/config-env/local/dotenv选项。已经持久化的 `media_transcription_v1` / snapshot_version=1任务继续按原provider_config_path恢复，不静默转成v2。未知snapshot版本明确拒绝。旧kind/键名、005已知调用缓存、未知结果禁止重放、partial产物保留与失败状态均保持。

006B作者验证：独立PG15470/live006b中，8项真实任务测试与19项registry/unit测试合计27 passed；覆盖直接按旧006 payload写入的旧任务执行、新v2完整任务、partial重试沿用已知调用、完整配置漂移在调用前拒绝、环境防降级、根.env隔离、每job授权与生产staging显式私有env。CFG最终描述型模型增量后，19项无DB测试再次通过。没有真实模型请求或下载。最终集成与QA证据另记reports/LIVE-006B。
