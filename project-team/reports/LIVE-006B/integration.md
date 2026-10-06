# LIVE-006B 集成验收记录

2026-10-06，ARC /root。相对基线74df3b1，独立批准CFG a2753fb、JOBS7216234；分批集成768c38f/951a91a/bccfbcf，工程前置b5a96d0。最终组合树待独立QA绑定后提交；本记录不是作者自批。

## 实际验收

- 新CLI v2与旧CLI v1：真实FFmpeg处理2200ms合成WAV，3段，全局起点0/1000/2000ms；两项任务succeeded，transcript complete=true/synthetic=true，snapshot版本分别2/1。v2优先级实际覆盖base4→development3→local2→dotenv1；max_duration dotenv12被系统环境10覆盖。合成dotenv无关私密哨兵不进入job快照。
- 烟测结果：runtime/live-006b/integration/5906a5c11e3a422b8e42f9ce73482e57/result.json；target.json登记live006b_suite_44d6a7d6a8ec4bf8a50e8da749a47d6f。两任务extraction/transcript JSON长度与SHA逐项复核通过，artifact-verification.json留证。
- 最终后端套件：204 tests、0失败/错误/跳过；runtime/live-006b/integration/eedd57296f82477d98a16056cd96fffc/pytest.xml；实际数据库live006b_suite_e06c6fc5fc6540d585f22f37dd512ccc，role live006b，端口15470。显式排除test_jobs_broker.py，不宣称本轮MQ端到端。
- 工程unit：36项通过，包括8项本轮目的/环境guard；Ruff按services/backend/pyproject.toml检查全部backend与scripts通过。一次未显式指定配置的Ruff读取工作区外默认规则而产生风格错误，按项目CI规定配置复验通过，未为了该差异改全库风格。
- QA先前亲跑CFG88项0skip、JOBS32项0skip，分别包含URL凭据逐层拒绝、LAN覆盖/设备深合并、timeout完整指纹、旧原始v1持久shape、缓存/partial重试、prod/dev防降级。不是将合成ASR说成真实模型质量。

## 变更、验收与边界

[逐文件新增/修改清单](file-manifest.md)；[完整配置改造说明](../../../docs/ai/configuration-refactor.md)。主checkout仅ARC串行集成；CFG/JOBS修改分别取已批准提交增量，没有覆盖共享配置或依赖锁。目录按core配置、ASR adapter、workers桥接和config共享文件分责；不创建空Agent/RAG。

没有DB schema迁移、依赖新增、前端修改、真实供应商调用、模型下载、远程PR或部署。HF/Ollama/YOLO与非ASR能力只有类型化描述，resolve拒执行。每任务网络授权、已知结果缓存、未知结果禁止自动重放和v1不可变输入保持。

回滚须停止v2任务或保留v2恢复兼容，不得把snapshot改成v1或删runtime证据。已有旧006/005库未修改；作者、QA及ARC测试库和产物全部保留。主suite和CLI进程已退出，数据库保留；最终独立QA会追加自己的烟测实物与SHA/树核对，PM另做范围验收。
