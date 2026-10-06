# LIVE-006 最终组合独立 Review

Reviewer `/root/qa_live002`；2026-10-06。

**批准候选 staged tree `a994b27d04d219301d27ac674f909f09b1ee56d2`**，主基准 HEAD `eb82bc0dfaac73ee28bbfb86800c744348a42636`。审查前后 write-tree 相同，无 unstaged 差异，staged diff --check 通过。提交必须保持此树并返回commit SHA供核对；新代码变化需重审受影响范围。

## 审查范围

已批准CFG519e313（集成5fa4469）、MEDIA1ce1b466be333598a8f37324c97f5bd1d916d953、JOBS802dfe8fe3597f5820cced34f3a4e1c5e73db6b3；独立逐字节比对MEDIA/JOBS生产Python及测试与组合main一致。检查最终driver、8项guard、scope登记、操作/能力边界文档、任务与集成报告。364行driver含目的守卫和烟测/回归两种入口，职责单一，无需按行数机械拆分。

无P0/P1。MEDIA空白误完整、缺时间丢原文、巨大时间戳、响应异常脱敏及限额修复均已独立审查。历史问题及证据见qa-media/qa-config/qa-jobs/qa-environment报告。

## QA亲跑与实物

- 最终8项LIVE-006 guard：全部通过，0.005s，模拟Docker不操作旧资源。
- 最终正式driver独立完整烟测退出0：实际登录→主播/场次→MP4上传/finalize/关联→operator submit/run-local→005独立handler→两阶段成功→GET job。结果 `runtime/live-006/integration/522d497025914348afdc128797a62e3b/result.json`。
- 独立核该烟测原片SHA、extraction/transcript引用文件的size/hash，真实WAV为16000Hz/mono/16-bit PCM/36864samples（AAC解码2304ms）；字幕synthetic=true、complete=true、全局起点0/1000/2000ms。所有文件在runtime内。
- QA此前真实PCM精确2250ms+500ms偏移样本、样本拼接一致、真实FFmpeg超时/取消清理、33项MEDIA测试、37项CFG测试、5项JOBS+3项独立PG/MockTransport探针均独立亲跑；详情各模块报告。
- 独立只读正式build_engine复核专属库 `live006_suite_5b40effdbeac4985b90da0c397d9f425`，role live006，迁移0004_jobs；证据 `runtime/live-006/qa-final-db.json`。没有打印凭证、改业务记录或触碰005库。

## 复核ARC证据（不冒充QA重跑全套）

独立解析 `runtime/live-006/integration/0604ddf208934df78e221ac1025bd835/pytest.xml`：126 tests、0 failures/errors/skips；明确排除broker-only文件，不能称本轮MQ全链验收。target.json与application-db.json匹配专属数据库；app/worker继承数据库URL，既有build_engine设置只覆盖options不覆盖database。实际jobs测试的新job在独立handler成功，避免旧库假成功。

前两次125pass/1fail证据保留，集成报告正确说明历史outbox干扰及search_path被覆盖原因；最后只在006专属PG内新增固定前缀UUID库，未删历史数据、未屏蔽失败测试、未改生产dispatcher逻辑。ARC的28工程tests/Ruff/policy结果作为其证据，QA未无必要重复完整套件。

## 交付边界与收口

真实本地FFmpeg产物、离线fixture、MockTransport及未验真实供应商四层分开。无真实模型请求/费用，无新的公开analysis-runs创建HTTP接口，无前端接入、视觉/报告/资产审核/抓取。请求数/时长是硬限制，金额仍为声明；未知调用不盲重试。独立代码批准不等同PM产品验收或发布。

P2文档收口：母卡顶行仍in_progress、旧作者23tests条目未标历史，与STATUS in_review相比略滞后；请后续纯文档收尾统一状态、标历史且写最终SHA。此项不影响代码树批准。PG15460锁已归还ARC；QA无运行进程或资源独占。待本树提交核对后再走PM收口，不提前标done。

## 提交后独立核对

提交 `649eb0759d1adf397e24f09b9ba458e612989939` 的 tree 为 `a994b27d04d219301d27ac674f909f09b1ee56d2`，与批准树完全相同；HEAD 指向该提交，核对时工作区 clean。本确认仅追加runtime，后续纯文档收口另行审查，不修改本次已批准代码树。

## PM 最终验收事实（ARC登记）

PM-01 `01a10b7c-30e0-7fa3-9545-0001d85a33b3` 于2026-10-06明确验收通过：已核代码649eb0759d1adf397e24f09b9ba458e612989939的树与独立QA批准一致、126零失败零跳过，亲核烟测hash与WAV。接受YAML配置、真实抽音、时间戳协议与005任务接线的限定范围；前端Demo和真实供应商未验，真实模型调用未授权。

PM授权纯文档收尾保存本报告、母卡与STATUS标done、旧23项自检标历史、记录代码SHA与释放资源。P2状态文字已修；产品代码不变。本收尾提交不部署、不建远程PR、不启动下一轮。
