# LIVE-021 真实场次与采集前端

Owner FE-01子代理/root/eng_live001；base a680ff75e9509a2f879bee0106695cb49d59bd18，feat/LIVE-021-frontend，.worktrees/LIVE-021-frontend。沿用现有React界面，不新建第二Demo。

/sessions与UUID详情接真实登录、主播/场次、采集/材料和显式手动本地ASR；旧示例详情保留在明确/demo/sessions/:id路径，不能套入真实报告/评分。抖音PC地址与视频号手机投屏分开；显示真实状态/错误、刷新恢复、幂等提交、停止请求和终态。健康或执行器未就绪时禁用开始，收到URL不算录制成功。录后材料播放/下载，不重复上传已入库文件，不自动调用云。

FE独占frontend/web/src必要文件、新交互测试及vite.config.mjs代理；不改站点部署文件/依赖锁，额外脚本修改先协调。后端契约由CAP持有，ARC持环境。npm build、站点及关键交互/浏览器验收，合成与真实平台分开记录；report LIVE-021，固定SHA交非作者Review。
