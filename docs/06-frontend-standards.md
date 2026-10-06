# 前端规范
基线是现有 frontend/prototype 的 React/TypeScript/Vite/React Router，整理后 frontend/web。保留确认的 UI 和全部路由，不重做第二套。
Tiptap/dnd-kit/Radix/lucide 已在清单；不要再声称使用旧模板 shadcn/TanStack Router。

pages 保持入口，复杂业务逐步归 features；components 只放真正复用 UI。API 生成物归 src/api/generated，统一请求错误处理归 src/api。
按页替换 fixture/store，服务失败不能退回假数据。服务器状态来自 API，未保存草稿保留本地。
写入携带 revision，409 保留草稿并提示差异，不自动覆盖。上传进度、分析阶段、媒体加载、保存状态分开；没有百分比就显示阶段。
前端不存密钥、不拼业务提示词、不自行决定最终审批。未知时间不跳 0；Range/过期权限/无文件有明确反馈。
新增专业播放器/PDF/上传库先小探针，不一次叠满依赖；沿用现有组件、焦点/键盘/排序按钮。
每页接入后构建/类型检查+真实浏览器操作+刷新/重新登录持久化+失败冲突验证，build 不等于 UI 验收。
保留 .openai/worker/构建脚本；适用时 npm run build 和 npm run test:sites，目录迁移验证原打包能力。
