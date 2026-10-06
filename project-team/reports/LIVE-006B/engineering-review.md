# LIVE-006B 工程与环境独立 Review

Reviewer `/root/qa_live002`；范围仅下列未提交文件，按内容SHA256批准。无生产模块批准，不操作DB/Docker，不动旧006环境。

## 文件指纹

- scripts/checks/live006b_environment.py：`42063e18ff2bc9ba9759dbc395933f39f1f6918be0eef1a2b1fb939e5d3fb4a5`
- scripts/checks/test_live006b_environment.py：`49bad7947663bb9247ecfdcd4401e61b24a1c538ae1fbfe3e2100111295c1ccc`
- infra/compose.live006b.yml：`4f4276d94f2ce0a39dca304e2359f4c3f481bede73c2da0427a06226db8fce4e`
- .gitignore：`a82f7440668b67522a6b6330ab0f18989f969134a3873d9dd2fe310b375a0967`
- scripts/checks/repository.py：`33b14f8bd48a1ce685c64506a195f6d72545e6aafde2b40da143cfa874c347b2`
- scripts/checks/test_repository.py：`dc1a2a24420beb58b6384334624a14a20f5ee9d275c0e11eecd364d8f4ced9c9`

## 独立验收

6项006B环境guard passed（0.014s），5项repository policy tests passed（0.198s），diff --check通过。额外独立探针确认嵌套private local override被门禁拒绝，默认/环境/公开示例及.env.example可跟踪，CFG/JOBS分支scope解析完整；git check-ignore实际确认本机local及嵌套*.local文件忽略。独立探针首次导入task_for_branch模块写错，修正为现有ci_policy后通过，无产品修改。

环境脚本相对已审006 guard仅适配006B独立目的：PG15470、live006b库/role、live-fde-006b项目、runtime/live-006b存储。继承Docker/Compose覆盖拒绝、本地unix context、主checkout、runtime重定向、private.env严格键/值/权限/普通文件/大小守卫保留；既有容器核归属和数据mount。Compose固定loopback端口/用户/数据库及image digest，无清库/删卷/启动MQ指令。QA只运行mock guards，未核实真实PG健康。

.gitignore仅加入本机local配置模式，默认models和公开example未被隐藏；repository允许config与根.env.example，另外拒local私有覆盖；新scope分别CFG/JOBS/ARC登记，无修改原业务scope。目录扩展需由ARC已授权的目录规范同步记录，最终组合审查再核。

结论：上述文件字节范围批准，无阻塞。后续CFG Registry验收将追加embedding/reranker descriptor、temperature/device/model_path/confidence字段约束，unsupported执行明确拒绝；descriptor可配置不等于已实现推理，禁止下载权重/外部调用。
