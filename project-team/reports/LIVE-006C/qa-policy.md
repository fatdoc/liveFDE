# LIVE-006C d8313bc shared增量 / 12b1c54 UI门禁独立审查

独立QA /root/qa_live001，2026-10-06。

## 固定对象与结果

- d8313bc8065a75b5fdab8ee0c442a15b271a0ef0 已导出固定代码到qa-d8313bc/snapshot；使用本人独占15480/live006c_qa_stream_20261006，未碰UI/作者库。API/gateway/recording/stream 40项真实PG或单元测试全部通过，50.79秒。模拟ASR，不真实云/模型。日志qa-d8313bc/tests.log。
- 其中旧stream测试mock了prepare，只验证WS安全/生命周期，不以其通过声称新revision0产品门禁在真实WS已验。真实API覆盖revision0拒绝、保存后使用、tenant/CSRF/revision、无grant fallback disabled仍可本地提交、expired stream不重排；CloudRecorder覆盖已知/未知意图不重放及过期共享worker必须核验停止。
- 此前两个P2已解决：fallback仅本次授权时检查云route；prepare拒绝revision0，先显式保存再任务CAS；policy非法schema安全码，不把GET偷偷写库。
- 12b1c5484021ae56c365658a245c6ffbf9c20aa9 UI差异独立静态批准：rev0未修改仍可保存；按钮/start均禁止试用；已有任务查询不受影响。首次新工作区浏览器回归仍待最终验收。

## 生命周期审查边界

stop_guard仅对asr.gateway/local建立停止确认回调，request_id为job:attempt与worker发送一致；handler父进程在子进程确已退出但未完成时要求cancel_and_wait，否则StopUnconfirmed，不能自动重试。过期asr_gateway任务也标stop_unconfirmed而非重排；未知云意图优先保留unknown。

这些共享代码的取消确认依赖尚未集成IPC实际实现；本报告批准policy/API修正及UI门禁集成，不批准IPC取消生命周期或006C整轮。

提出的外层stream.consume直接return completed未用aclosing问题，ARC确认已交IPC/WS作者处理。须在新版联合审阅确认provider finally完成后才finish/对客户端完成；当前未声称发现持续推理泄露。

无源码/index修改，测试结束，QA数据库保留证据。现有httpx/Starlette弃用提示非失败。
