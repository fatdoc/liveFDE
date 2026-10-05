# LIVE-004C 本地变更单（作者自检，不是独立批准）

## 范围与依赖
owner BE-02，执行子任务 `/root/eng_live002`。基础 da128af，按ARC授权引入A身份996b4f4及B场次d76009e作为开发依赖；依赖合并不是批准。C自有路径见任务卡，不改main/core/config/锁。

## 已实现
- PostgreSQL持久上传幂等键+请求hash、输入/实际大小、SHA256、显式用途和格式；初始化冲突409。
- 流式PUT、固定大小上限、无续传、独立UUID暂存key与原子完成标记；过期410，竞争409，失败可重新PUT。
- DB行锁+lease token；锁定读取populate_existing，避免expire_on_commit=False的旧identity map夺回新租约。每次finalize写不同UUID候选文件，旧worker不覆盖新blob。
- finalize校验真实MP4/WAV/MP3（ffprobe强制demuxer，仅file/pipe协议，30s超时），UTF8逐字稿（10MiB），实际pypdf解析参考PDF（20MiB，不接收加密/空PDF）。PDF不会作为原话证据，不允许primary关联。
- workspace内hash去重，物理blob与用途material分开；并发由unique约束兜底。DB提交失败前保留源文件，可恢复重放；完成的upload禁止再次PUT。
- 场次多材料关联及重复关系200；不同场次可使用同一材料。新增GET场次材料分页，经ARC明确授权，刷新后可找回材料。
- 所有读取先workspace授权；UUID只用于存储key，filename仅展示，无URL下载。
- GET单Range206、越界416/Content-Range、语法400、多range完整200、If-Range不匹配完整200；HEAD按ARC决定忽略Range/If-Range返回200完整metadata空体；401/404仍优先。
- init/PUT/finalize/metadata/link/list已声明response_model，错误code统一snake_case。

## 接线与迁移
0003_materials →0002_sessions→0001_identity。
ARC负责main include材料router(prefix='/api/v1')及Alembic env import materials.models。测试显式组合真实模块/真实身份/真实PG，没有替代后端stub。
需配置storage_root；未配置503，不落cwd。依赖pypdf==6.19.0由A锁定。

## 测试证据
命令从C工作树运行：
```sh
uv run --project services/backend --env-file ../../runtime/live-004/4c.env python -c 'import os,subprocess,sys; os.environ["LIVE_TEST_DATABASE_URL"]=os.environ["LIVE_DATABASE_URL"]; sys.exit(subprocess.call([sys.executable,"-m","pytest","services/backend/tests/test_materials.py","-q"]))'
```
真实PG15440独立live004_4c；合成媒体仅runtime/live-004/fixtures-4c及storage-4c；日志runtime/live-004/materials-tests.log。
15项包含：持久/并发幂等、两finalizer同hash并发、双Session旧lease隔离及旧failure不覆盖、DB提交故障恢复、真格式与伪装playlist拒绝、大小/hash/短流重试、跨workspace读取先于Range、两场关联+刷新列表、HEAD/Range、两个独立Uvicorn进程先后启动读回原字节。已运行通过；Starlette/httpx兼容弃用警告保留。
Ruff按项目配置通过，版本迁移通过。正式应用main接线/完整组合Alembic check由ARC集成后验证。

## 边界/风险
不含云模型、ASR、URL采集、断点续传、业务分析。lease TTL默认300s；长流仍以token隔离，活跃长上传可能被到期重试抢占并返回409，不会覆盖最终文件。
候选/过期暂存保留在runtime，尚无定时GC，不混删原始blob。暂存数据占用需后续运维策略；不伪称已清理。
PDF解析有20MiB上限；生产高并发/恶意资源消耗测试、独立解析沙箱和磁盘配额属于后续部署加固，未声称验证。
测试API进程只绑定临时loopback端口，结束已停止；不是常驻预览。

## 回滚
代码revert，受控空开发DB可按逆序downgrade；不删客户数据/用户卷/原片。审核必须绑定最终C提交SHA，集成由ARC串行执行，本作者不自批。

## 独立评审修正
QA指出初版fixture直接写入platform=manual，超出正式API枚举。已将专用fixture统一为other，并在每个测试初始化后通过正式GET /api/v1/sessions/{id}验证200且platform=other；不再仅依赖ORM插入成功作为场次有效证据。该修正仅涉及测试/报告，后端行为未改变。修正后完整15项真实PG材料测试重新通过，Ruff通过。

## 集成OpenAPI修正
将材料content的GET/HEAD分别注册并显式指定get_material_content/head_material_content，避免同一api_route生成重复operationId。新增全量OpenAPI ID唯一性测试，强制重建schema并把重复ID警告当失败。修正fixture对当前FastAPI惰性IncludedRouter的检测：使用公开OpenAPI paths判断模块是否已组合，避免反复include；真实进程重启fixture也兼容正式main已经接线。完整16项真实PG/HTTP/进程重启回归通过（19.20s），仅保留既有Starlette/httpx弃用警告，没有Operation ID警告；Ruff通过。
