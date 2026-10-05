# LIVE-001 独立 QA 静态审阅

- 日期：2026-10-05
- reviewer：独立子任务 /root/qa_live001；未参与搬迁、源码编辑、staging 或提交。
- 审查对象：staged tree `ce007e610c5bf037b5c5bf6d833a049554af68b7`，94 个文件；base 无，首次基线。
- 结论：源码与目录迁移可接受，未发现 P0/P1；以下 P2 治理文字需收尾或 ARC 明确处置后提交。最终新 tree 须仅对变化部分复审。

## 独立复核

1. 直接读取 index blobs 扫描禁入文件路径，以及私钥头、云密钥形态、带密码 URL、长 token/password 赋值；候选命中 0。仅扫描本次待提交内容，未读取原私有配置。该启发式扫描不等于形式化无密钥证明。
2. index 内无 node_modules、dist、runtime、客户音视频/PDF、数据库、私钥文件。仅两张生成 UI PNG 素材；CPB manifest 为文件路径/SHA256清单，不包含源文件内容。
3. 对 migration.json 所列 41 个 Demo 文件逐项重算 staged SHA256：全部匹配 after_sha256；39 个与搬迁前一致，2 个差异为 README/design-qa 文档。业务源码、依赖锁、hosting、worker、测试内容保全。
4. 17 项本地归档重新统计普通文件数与字节数，全部匹配搬迁前登记（不跟随依赖软链接）。未用本次计数冒充逐文件历史哈希证明。
5. package.json 与锁文件根 dependencies/devDependencies 一致；入口脚本指向 frontend/web；worker 和打包脚本使用相对运行根，不依赖旧 prototype 路径。
6. `npm --prefix app/frontend/web run test:sites` 独立运行 4/4 通过，包括静态资源、SPA fallback、非HTML/写请求边界、hosting产物检查。实际云 hosting 未部署。
7. `git diff --cached --check` 通过；检查时 index 与工作文件内容一致。
8. 外层 docs 是符号链接；design/ui-prototype-20261003 存在且不是符号链接。后端目标目录尚未创建，符合不创建空壳模块要求。

## P2 治理文字修正

- `docs/operations/live-001-migration.json` 的 notes 将 design/ui-prototype-20261003 写成 symlink，实际为普通目录；应更正。
- 同一 JSON 的 archive_exists:false 是搬迁前事实，当前归档已存在；建议改名 archive_existed_before:false，避免清单在 validated 阶段表达错误当前状态。
- `project-team/access/RESOURCE-LOCKS.md` 仍写“清点中，搬迁待 ARC 清单审查”，需要随本轮收尾更新为已搬迁/交接。STATUS、任务、review 的进行中事实应由 ARC 在提交及 worktree 验证后按实际更新，不提前伪填 done。

## 未测范围

浏览器交互与视觉回归由 ARC 独立执行；本人没有重复操作浏览器。本审阅未重新 npm ci、未做依赖供应链安全审计、未部署 Sites、未调用模型、未运行后端/数据库、未访问原 CPB 服务。首次 commit 和 worktree 生命周期尚待 ARC 执行。本批准范围不涉及这些未完成门禁。

## 差异复审与最终静态批准

独立复审 `ce007e610c5bf037b5c5bf6d833a049554af68b7` → `e61ac5e761e0e8c5949f3a4f0fdc3e82e2cb0199`。仅 4 份治理文件、8 增 7 删；未改变源码、依赖或素材。三项 P2 已消除：design 改为普通目录，archive 字段明确 before/after，资源锁与任务状态更新为搬迁后审查阶段。没有预填首次提交或 worktree 成功。

结论：批准 staged tree `e61ac5e761e0e8c5949f3a4f0fdc3e82e2cb0199` 作为首次产品基线提交；静态审查无剩余阻塞。浏览器最终验收仍由 ARC 负责，提交后还需实际验证 worktree 并记录真实 SHA。若再变更内容，复审变化部分。
