# LIVE-001 工程目录与 Git 首次基线
- 状态：done（2026-10-05，技术验收与 PM 业务核对通过）
- owner：ENG-01；技术 reviewer：ARC-01 独立窗口；QA：QA-01 按需独立验证
- 目标：干净、可追踪的独立产品目录，现有 React Demo 保留可运行。
- 范围外：不改业务 UI、不实现后端、不启动原 CPB、不创建/推送远程。
- 依赖：docs/04 目标目录、docs/09 首次基线例外。
- 允许路径：app 内现有 CPB 存量目录的登记搬迁、frontend/prototype→frontend/web、根入口/.gitignore/.dockerignore、docs/operations、project-team 当前任务；工作区 archives 内独立 cpb-reference 归档。
- 不允许：原 CPB 源仓库、第一次需求拆解、其他工作区；不读取/打印密钥内容。
- branch/worktree：首次基线前仅主 app checkout 串行；base SHA 无。
- 资源：先查运行进程/端口/软链接，不能静默移动仍在提供预览的 cwd。
- 回滚：搬迁清单记录旧新路径，旧材料保留；失败按清单恢复，不覆盖同名归档。

## 执行与验收
1. 清点源码/配置/运行产物/设计软链接，记录路径和大小；来源参考 docs/operations/cpb-source-manifest.json。
2. 提交精确搬迁清单给独立技术 reviewer；归档只作本地参考，含私有材料不打包。
3. 保全迁移前 Demo，迁移后验证依赖锁/构建/原路由/静态资源/hosting，重新确认预览入口。
4. 更新 ignore：不要用通用 models/ 忽略合法源码；精确忽略运行模型权重路径。检查所有待入库文件类型/体积/敏感内容。
5. 只 stage 新产品规范与经过检查的 Demo 等明确路径；独立审查 index 与清单。
6. 首次提交 main，记录 SHA，确认 git status 与所有未跟踪项的处理；不删除保留材料。
7. 验证可从首次 SHA 创建并移除一个无改动试验 worktree，再允许并行。

## 交付
ENG-01 执行任务：/root/eng_live001；ARC-01 当前任务独立审查及浏览器验证。当前先清点，搬迁与 staged 内容分别审查后再推进；不预填通过。

### 实际交付
- 前端 frontend/web；CPB 归档 archives/cpb-reference-20261005；历史原型产物 runtime/prototype-qa-20261005。
- 20 项搬迁完成；41 项 Demo 文件39项哈希不变、2份路径文档更新；源码/锁/素材/hosting不变。
- build、hosting 4/4、10路由/图片、审核→学习库→备播、报告修订与导出预览通过。
- 独立 QA：/root/qa_live001，批准 tree e61ac5e761e0e8c5949f3a4f0fdc3e82e2cb0199。
- main 首次/代码集成 SHA：13665739fb29d8aa70a9e78d32bce3d58c81bd0f；后续状态记录提交不改变该代码基线。
- 工作区内试验 worktree 已成功建立、核对、移除；当前无遗留试验分支或改动。
- 详细验证和限制：[验收记录](../reports/LIVE-001/qa.md)。
- 预览：http://127.0.0.1:5188/；Git remote 未配置，未发布。
- PM-01 任务 01a10b7c-30e0-7fa3-9545-0001d85a33b3 已明确最终业务核对通过；范围仅 Demo 保全、目录/Git基线，未扩展为后端/下载打印验收。本轮不启动 LIVE-002。
