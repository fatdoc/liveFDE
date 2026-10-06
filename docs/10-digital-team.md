# 数字员工
用户是项目所有者；PM 管范围和排期，ARC 管技术/目录。角色是责任，不代表七个常驻进程或 GitHub 账号。
路径相对 app，整理前 frontend/web 对应 frontend/prototype。旧 CPB 无正常开发写权限。

| 岗位 | 默认写范围 | 独立评审/限制 |
|---|---|---|
| PM-01 产品/项目 | docs/01、05、08；project-team/tasks、STATUS、业务验收 | ARC 审技术影响；不改代码/权限 |
| ARC-01 架构/目录 | 技术规范、adr、contracts、AGENTS、project-team/access | 自己实现由其他 owner+QA 审；介入代码需任务路径 |
| ENG-01 工程/集成 | infra、scripts、.github、清单/锁/工程配置、README/TASK、operations | ARC+QA；唯一串行集成，不代替技术批准 |
| BE-01 后端 | services/backend/src/live_review/{core,modules,workers,integrations/storage}、migrations、对应 tests | ARC/独立后端 Reviewer+QA；不改 AI prompt/前端 |
| AI-01 媒体模型 | services/backend/src/live_review/integrations/{media,asr,vision,llm,capture}、prompts、对应 tests | ARC+BE 契约审查+QA；不直接写业务表 |
| FE-01 前端 | frontend/web/{src,public,tests}、前端文档、生成客户端 | 独立 FE Reviewer+QA；清单/锁/构建配置交 ENG |
| QA-01 独立验收 | 对应 tests、project-team/reports、docs/qa | 不改生产逻辑或放宽断言；修复转原 owner |

analysis 正式 schema 归 BE，AI 提案后 ARC 冻结；prompt 归 AI；storage 归 BE。
PRODUCT 产品入口 PM 维护，README/TASK ENG 维护，AGENTS ARC 维护。未列路径先归属再改。
测试重叠需任务精确到文件；锁/OpenAPI/生成客户端/迁移 head 登记唯一持有人。
岗位路径是协作约束，不是 OS/Git 强制隔离。

## 多窗口
W0 统筹/架构/集成（PM/ARC/ENG 职责分别记录）；W1 后端；W2 AI；W3 前端。
用户现已要求独立 PM 窗口：PM-01 专门对接用户，原任务改为 ARC-01 技术统筹，PM 不再混入 W0。其余窗口按实际任务启用，命名和互通规则见 13-window-collaboration.md。
W-review 按需启用/替换空闲执行窗口，独立读指定 SHA，不把作者“通过”当证据。
窗口可先后换岗，但同一变更不能换名自审；缺 reviewer 保持待审。
新增员工必须有明确独立任务、路径、reviewer 和并行收益，不为人数造层级。
临时扩权由 ARC 记录精确路径/理由/任务/失效；不能扩大用户业务/生产数据授权。
