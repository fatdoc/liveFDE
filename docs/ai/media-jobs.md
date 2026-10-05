# LIVE-006 媒体任务队列接线

沿用LIVE-005 Job/Stage/Outbox/Context，不建立第二套任务状态。注册名media.extract和media.asr；resolve只允许固定注册，不接受payload动态导入。抽音和转写共用已有material和workspace边界。

本模块分工：media_jobs负责材料核对/阶段；media_calls包装逐段调用意图与已知缓存；media_artifacts负责受控JSON产物；media_operator是本地操作员入口。未新增任意任务创建HTTP API。

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

提交和执行均核active admin/workspace/material；只接受同workspace session_media，读取Blob受控UUID键，固定原SHA/字节数并在实际抽音后再次比对。提交持久化无密钥provider snapshot、当前YAML绝对路径、material ID、source hash/size、storage fingerprint和授权标志。配置/存储漂移、管理员停用、材料改变均阻止执行。

提取和ASR产物位于storage/jobs/<workspace>/<job>/<lease-token>/，产物名随机UUID，JSON 600、目录700，引用相对storage根附SHA256/长度。先写完fsync再允许stage成功；结果数据库仅保留小引用/统计，不塞完整transcript。阶段间读取验证长度/hash；路径逃逸和符号链接拒绝。新lease用新目录，不覆盖历史产物。

ASR每段在provider调用前begin_paid_call，已知响应先存JSON再finish记录引用；已知错误也finish存安全错误码。重试相同job/chunk复用已知响应/错误，不增加调用次数；未知响应留intent并传播call_result_unknown，005禁止自动重放。所谓paid intent也用于合成fixture，用于验证机制，不能当作本轮实际付费证据。

整场预检请求段数/音频总时长；真实adapter另逐请求计数。相同job不会通过重试绕过已知/未知结果缓存。金额是配置声明而非实时账单硬cap。部分转写先落盘并记录stage.artifact.complete=false，然后阶段失败；extract成功产物在重试保留。不能把partial标记任务成功。

## 验证与限制

作者在独立PG15460/live006运行test_media_jobs.py：5项通过，真实FFmpeg抽取2.2秒合成WAV并切3段，子进程Job完整成功；partial保留且重试沿用3条已知调用；跨workspace/停用管理员/配置漂移拒绝；未知调用两次请求只触发一次provider；已知响应不重复调用。Ruff通过。完整004上传→场次→job的集成smoke及独立QA由ARC另行记录。

测试命令需显式LIVE_TEST_DATABASE_URL指向独立测试库，否则集成用例skip。产物由测试tmp_path保存；运行交付产物仍在runtime受控storage。不把本测试宣称真实ASR质量/供应商可用性、字幕业务表、复盘报告或前端接入完成。
