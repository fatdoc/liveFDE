# LIVE-024 抖音解析空白Cookie修复

ARC owner，base ddcfb974，fix/LIVE-024-douyin-parser，工作副本.worktrees/LIVE-024-douyin-parser。用户真实试录run546dd419失败source_parse_failed；handler已停止，无媒体。离线h11已复现空格Cookie被拒绝，不能据此假定唯一原因。

ENG-02仅负责bridge/providers与对应test_capture_bridge/test_capture_providers；ARC登记/配置/运行/集成；QA-02非作者固定SHA审查。精确路径见repository.py，无依赖迁移/评分变化。无Cookie必须显式不发送，不能退回上游内置旧Cookie；只白名单错误分类，不打印异常文本/原始响应/Cookie/临时URL。已授权来源经修复Review后最多一次短时复验；先确认无活跃旧任务，保留所有失败。禁止被拦探针及变体。不扩大HTTPS/域策略、不绕平台登录/风控。

实现676c439已独立109通过；一次真实前端复验返回source_empty_response，进程停止无媒体。原库对照完成，FLV偏好差异记录但未混入本修复；正常浏览器/有效会话待PM确认。工程修复与真实平台验收分开，详见reports/LIVE-024/delivery.md。
