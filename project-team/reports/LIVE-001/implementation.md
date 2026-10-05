# LIVE-001 ENG 实施与验证
执行者：ENG 子代理 /root/eng_live001；审查者另由 ARC 执行。本记录不构成作者自批。

## 实施结果
ARC 已批准 inventory/JSON 20项清单。全部使用同卷 rename，目标存在即停止；17项旧CPB路径已归档，原路径不再混入产品目录。原根 ignore 配置额外保全在归档根。
frontend/prototype → frontend/web；qa/tmp → runtime/prototype-qa-20261005。源 CPB 和客户资料未改。
17项归档的普通文件数和字节数全部与搬迁前清点一致（两次均不跟随依赖软链接）。
41项Demo内容核对：39项SHA256相同；只有README/design-qa的历史截图路径文档发生预期修改。业务src、锁文件、静态素材、hosting、worker、tests未改。

## 实际命令与结果
- npm --prefix app/frontend/web run build：通过（tsc --noEmit + Vite + Sites packaging）。
- npm --prefix app/frontend/web run test:sites：4/4通过。
- dist/client/index.html、dist/server/index.js、dist/.openai/hosting.json：均存在。
- 新Vite从frontend/web启动：127.0.0.1:5188，PID 69984，旧prototype进程先显式停止。
- 扫描产品候选文件（排除.git/node_modules/dist）中的.env/key/pem/media/pdf/db文件：[]

## 较大候选文件
- frontend/web/public/assets/presenter.png: 1960649 bytes
- docs/operations/cpb-source-manifest.json: 2999006 bytes

## 风险与未测
既存Vite主JS约772KB（gzip246KB）有分包提醒，本任务不做业务打包重构。
浏览器路由/交互由ARC独立检查；本记录不代替浏览器验收。未调用任何付费模型、未运行后端/数据库/CPB、未发布Sites或其他远程。
不stage不提交；首次提交/独立Review/worktree验证交ARC处理。
回滚：按migration.json moves逆序恢复，目标存在时先停止；根ignore旧内容在归档根。
