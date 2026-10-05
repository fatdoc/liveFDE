# LIVE-006 JOBS 独立审查

Reviewer `/root/qa_live002`；源码 SHA `802dfe8fe3597f5820cced34f3a4e1c5e73db6b3`，live-006-jobs 工作树 clean。当前JOBS接线范围批准；依赖MEDIA已知完整性修复后仍需组合复审和ARC正式上传入口烟测，不能视为整轮完成。

## 亲跑

通过受控运行脚本 `runtime/live-006/run_qa_jobs.py` 固定本轮private.env，核 scheme/user/host/port/database = postgresql+psycopg/live006/127.0.0.1/15460/live006、无query/fragment，固定不可用broker端口1。未打印密码，没有接触005。

作者5项真实PG测试 + QA独立3项探针：8 passed in 6.90s，无skip。JUnit `runtime/live-006/qa-jobs.xml`；小型合成产物保留 `runtime/live-006/qa-jobs-pytest/`。仅一项Starlette/httpx弃用提示，与本轮失败无关。Ruff和diff --check通过。

亲跑覆盖真实FFmpeg→旧runner独立handler→持久化extraction/transcript与三条known intent；partial落盘且任务failed，重试保留extract、复用已知调用；workspace/停用actor/配置漂移；unknown禁止重放。

QA独立 `test_qa_protocol_jobs.py` 在真实PG Context上使用实际OpenAICompatibleASRProvider+MockTransport：
- 第一次HTTP成功→先保存response JSON→known intent；重建provider/wrapper第二次读取缓存，累计HTTP仍1次，结果一致。
- 第一次HTTP ReadTimeout→unknown intent；重建wrapper第二次不触发HTTP，累计仍1次。
- 正式submit默认未授权时，注入ForbiddenEnv.get及httpx.Client陷阱，两者均未执行，先返回network_not_authorized。

以上仅合成响应/合成密钥，未发真实外网ASR请求、没有费用或真实识别质量证据。

## 审查结论与边界

复用005 Job/Stage/Outbox/租约，固定handler注册；本地operator入口核actor/workspace，当前没有任意HTTP任务创建接口。提交固定材料hash/大小、配置snapshot/storage指纹；执行再次核验。source只读blob受控路径，产物按workspace/job/lease-token独立目录，先fsync后数据库引用，读取校验hash。partial先保存引用再失败，不冒充成功。

RecordedASR逐不可变segment hash登记intent；已知响应/错误复用，未知或任意未分类provider异常保持unknown，不自动重放。当前整场预计段数/时长限制，不能把声明金额当精确货币cap。配置变化阻止旧任务，不能重新算路由/预算。真实调用的授权已由本地operator显式flag与配置共同控制。

数据库锁在测试结束后已归还ARC，QA当前不占用PG15460。尚待MEDIA新SHA与最终组合树复核，以及ARC通过004实际上传产生material后的正式operator smoke。不得宣称前端、字幕业务表、报告或真实供应商已完成。
