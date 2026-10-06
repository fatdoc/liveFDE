# LIVE-027 FE 时间戳交付记录

日期：2026-10-07。作者角色 FE-01；独立 Review/合并由 ARC/QA 完成。
基线：dfa022a。工作副本 `.worktrees/LIVE-027-frontend`，分支 `feat/LIVE-027-frontend`。

## 行为

材料转写展示毫秒精度起止时间、时间戳来源和识别来源。VAD/VAD 分窗明确为区间边界，provider 时间戳也不承诺逐词对齐；未确认来源保留未知提示。ASR 完整度与整场直播采集覆盖率分开说明。

每张材料卡有独立 audio/video 引用；点击有效区间只设置本卡播放器 currentTime，不调用 play。元数据未加载、媒体错误、未知/非有限/负数/逆序/零长度/超出材料时长区间均不能定位，点击时再次校验真实播放器状态。保持原提交、查询、sessionStorage 恢复机制。

## 验证

- `node --experimental-strip-types --test frontend/web/tests/material-transcription-timeline.mjs`：3/3 通过，覆盖毫秒显示、非法边界、来源描述。
- `npm --prefix frontend/web run build`：通过；保留现有 bundle 大小警告。
- `npm --prefix frontend/web run test:sites`：4/4 通过。
- Playwright CLI 独立 Edge 会话 `live027-ui` 执行 `frontend/web/tests/material-transcription-browser.js`：通过八组断言；A/B 两张材料分别定位 1.25/4.5 秒，互不影响且 paused=true；恢复查询阶段零 POST；随后两次 POST 均被合成路由拦截，用于证明当前卡片提交关联；sessionStorage 恢复与手输其他材料任务只读展示且不能定位。

浏览器验证使用合成 API 响应与注入媒体元数据，等待空媒体错误后模拟元数据恢复；证明 UI 状态、定位调用及隔离，不证明真实媒体解码/播放/听核准确率。未调用真实模型、采集平台、提交或重试真实 ASR。ARC 已告知现有真实 job974e38db 调用失败 stage_failed，停止 ACK 已确认；真实时间戳验收仍待成功结果。

独立静态预览曾使用已检查空闲的 5205 端口，未重启 5199 或 API。临时 node_modules 链接仅复用本工作区已安装依赖，不提交。

## 边界与回滚

现有响应不提供 material_id，因此仅当前页面生命周期内由当前卡片提交并得到 job_id 的结果可以定位。手输恢复、旧 sessionStorage 仅保存 job_id、刷新后恢复的真实任务均只展示结果，提示归属未确认且禁止定位；不能靠重新提交真实 ASR 绕过此限制。后续如需恢复任务定位，由 ARC 协调服务端可验证材料归属契约。未知来源但数值有效的区间仍明确来源未知，不伪称服务质量。

本轮无依赖、后端、迁移、共享契约变更。回滚本次前端提交恢复原展示，不影响已保存任务和媒体。
