# LIVE-015～017 提前开发：统一直播采集

状态：in_progress。2026-10-06用户在CAP任务直接授权；ARC已读取原始请求核实。Owner任务 `01a11105-8328-7283-b726-8e9d34e75c36`，标准名“直播FDE｜CAP-01｜直播采集接入”。PM仍为 `01a10b7c-30e0-7fa3-9545-0001d85a33b3`，ARC为 `01a0ff89-4e64-7242-a012-92850d916a87`。

基线 `61c2cbbf6f74f20d752374a96bda09abba0209ed`；分支 `feat/LIVE-015-capture`；已实际创建 `.worktrees/LIVE-015-capture`。运行产物 `runtime/live-015/`，不入Git。API8197/助手8198/PG15490登记时无TCP监听，启动前再次核查；数据库使用独立live015或该前缀的唯一测试库，不能迁移旧轮库。5196/8196/15480与既有模型worker保留。

## 可独立验收的分段

1. 015A：固定上游commit/许可证/依赖和实际接口证据；统一probe/start/status/stop/health契约及状态模型。上游为ihmily/DouyinLiveRecorder与gtoxlili/wechat-finder-dlna，先核源码不凭旧博客。
2. 015B：抖音解析/未开播/录制/停止/断流与地址过期；受控进程、磁盘限额、关闭确认、完整或中断manifest。
3. 016：视频号本地投屏助手，等待投屏→收到地址→真正录制分开；实际手机/局域网步骤经PM集中提供，不把它写成云端自动抓取。
4. 017：关闭后材料导入、场次关联、去重/重启恢复；首版手动触发现有ASR，超时长标待转写不把采集成功改失败。自动转写若以后开启仍须既有隐私/预算授权。

同一owner可按依赖串行推进，在可审SHA逐段独立审查。没有样本不阻塞接口/失败恢复开发，但不宣称真实平台可用。范围不含弹幕、订单、成交、评分或报告。

## 唯一写入责任

CAP只在独立worktree开发：`integrations/capture/`、`modules/capture/`、`workers/capture*.py`、`tests/test_capture*.py`及对应fixture、`docs/capture.md`、本轮报告、公开capture配置示例及本轮环境脚本。

为实现完整接线，ARC本轮明确委派CAP为以下共享文件的唯一作者，ARC不并写：`main.py`路由注册；`core/config.py`仅capture配置；`workers/handlers.py`仅capture注册；`modules/materials/`必要导入接缝；`services/backend/pyproject.toml`和`uv.lock`必要依赖；`migrations/env.py`模型注册和唯一新增`0006_capture.py`。迁移revision定为`0006_capture`、down_revision精确为`0005_asr_settings`，不改旧迁移、不新分叉head。若有额外共享修改，发具体路径和理由给ARC协调，不需用户转述。

新增捕获配置复用安全YAML读取/分层机制但保持独立schema，不给旧Model Registry类型加入默认字段而改变v1/v2快照。Cookie/token/签名URL仅受控秘密引用，不进Git/普通日志。先发schema/接口/依赖概览给ARC进行普通技术协调，再随代码审查；不是用户审批门槛。

ARC持有main、任务台账、窗口登记、结构scope检查与串行集成。owner不得改main checkout或顺手提交ARC文件；模块与共享接线一起交独立Review。没有remote，使用本地变更单，不声称已建PR。

## 独立验收安排

首个reviewable SHA由CAP发ARC，附base/head、精确路径、迁移head、上游commit/许可、测试命令/实物和剩余缺口。ARC启用非作者QA（既有 `/root/qa_live001` 可复用，当前仅预登记未启动本轮审查），固定SHA审查，P0/P1修复重审。ARC最后串行集成、跑适用原有回归，PM作范围验收；未经这些步骤不标done。

至少覆盖鉴权/工作区隔离、无效链接/未开播、重复开始/回调/导入、主动停止与进程确停、断流/过期/崩溃/重启、磁盘不足、视频号三种状态、真实媒体音视频/可播放/时长、导入关联与现有ASR入口。不靠文件暂时不增大猜完成；采用明确完成事件或原子关闭交接，API确认导入前保留源文件，manifest保持实际时间/片段顺序/哈希/中断原因。

模拟协议、本地真实媒体、真实平台录制和真实ASR四种证据分开；真实平台/手机操作所需条件集中交PM，不能自动借用CPB账号或假设腾讯凭证已存在。不新增付费模型调用，不部署客户环境，不清理他人产物。
