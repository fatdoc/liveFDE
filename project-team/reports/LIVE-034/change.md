# LIVE-034 正常HTTP结束的模型测试修复

运行Python3.11的HTTPResponse.read1在Content-Length归零时关闭response.fp及其transport。原循环再次settimeout触发EBADF并被归为结果未知。本地真实HTTPServer只发送合成合法JSON、Connection:close时，修复前稳定失败，修复后完整长度/HTTP1.0/chunked/EOF响应均成功；截断长度/缺chunk终止/缺trailer与超时继续拒绝。

循环改为只在response未关闭时读取；仍在结束后检查deadline、剩余length与JSON/usage。连接失败、发送后断连、TLS、协议与客户端错误分开；日志只输出阶段/类别/稳定错误码/unknown布尔，页面补相应指导。不记录原始异常、地址或服务内容。

13:51与13:52真实请求只保留llm_result_unknown，底层原因无法追溯；已复现缺陷不等于证明这两次的唯一根因，更不把修复后离线通过当作真实模型成功。历史unknown与request tombstone原样保留。本轮不发送真实模型请求、不修改配置、不发起录制/转写。

作者针对性测试和独立QA/CI/部署结果见runtime/live-034；修复前证据local-repro-before.log。回滚切回35835e2代码并保留所有私密数据，旧版本可能重新误报正常关闭连接。无API字段、依赖或迁移变化。
