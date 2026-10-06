# LIVE-006B JOBS 独立 Review

批准源码 SHA `7216234d4f72e57264afba0e1f20de52bc753098`，tree `2f08356a6e7d89c66e7c7f31bfceb7515c070250`。审查增量c04d390+7216234（CFG依赖已另批），工作树clean。

独立新建专用PG15470库live006b_qa_a29eec20dd6d4541b6015701137d2918，固定live006b角色、无query且不可用broker端口1。正式build_engine验证实际current_database。亲跑8真实PG任务测试+24桥接unit：32 passed in20.59s，无skip；Ruff/diff通过。JUnit/实际产物在runtime/live-006b/qa-jobs/同名数据库目录。库保留，锁已归还ARC，未动旧006或006B主库。

审查v1按原payload直接create_job、无新增locator/model_id/runtime_environment仍恢复执行，input原样保留；v2完整快照/locator/env/所选模型固化、漂移及未选模型变更拒绝、partial重试沿用known缓存。factory集中ASR且能力错配拒绝；005 unknown/取消/租约未改。CLI明确互斥--config与--config-dir；v1拒新选项且无dotenv加载。dev/prod正规化后做可信环境检查，production+dev不可降级；CLI别名解析新增回归已亲跑。

默认逐任务allow_network仍false，Settings与os.environ不被模型dotenv污染，秘密不进任务payload/产物。测试只合成文本/密钥，不联网/下载，不代表真实识别质量或费用控制。既有Starlette弃用warning一项不影响结果。QA runner初次输出脚本用错工作目录，在任何DB动作前失败，纠正绝对/根路径后上述唯一实际运行成功，未修改产品源码。

结论：模块批准，无P0/P1。正式组合driver与主分支集成树仍需最终验证；没有全平台功能或PM done批准。
