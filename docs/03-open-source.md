# 外部组件
选型不等于已集成。CPB 参考见 [11](11-cpb-media-pipeline-audit.md)；旧 FastAPI 模板已归档，不是当前代码基线。

| 组件 | 用途/状态 |
|---|---|
| FastAPI、SQLAlchemy、Alembic、PostgreSQL | LIVE-002 基础环境待验证 |
| Celery、RabbitMQ | LIVE-005 任务 |
| FFmpeg/FFprobe | LIVE-006 媒体 |
| DashScope ASR、Qwen VL、DeepSeek | 自有账号，待真实模型探针 |
| ReportLab | LIVE-008 导出 |
| sherpa-onnx、3D-Speaker | 多人场景按需延后 |
| DouyinLiveRecorder | M5 抖音候选，未集成 |
| wechat-finder-dlna | M5 视频号投屏候选，未集成 |
| React Router、Tiptap、dnd-kit、Radix | 已在 Demo 清单，兼容以实际构建为准 |

逐模块迁 CPB，不整体复制运行依赖。引入时记录 URL、commit/version、源路径→目标路径、修改、许可声明和测试，统一 docs/operations/dependencies.md（实际引入时创建）。
不复制凭据/客户数据；不同仓库许可证不能一概视为 MIT。许可和来源记录随交付整理，不追加普通开发审批。
不为编排先加 Dify/LangChain 等平台。

官方入口：
- https://fastapi.tiangolo.com/
- https://docs.sqlalchemy.org/en/20/
- https://alembic.sqlalchemy.org/
- https://docs.celeryq.dev/
- https://github.com/ihmily/DouyinLiveRecorder
- https://github.com/gtoxlili/wechat-finder-dlna
