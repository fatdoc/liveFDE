# LIVE-006 环境与参考说明独立审查

Reviewer `/root/qa_live002`；主代码基准 main `5fa4469`。本报告绑定未提交文件字节，不代表整个 main 未提交差异批准。QA 没有访问数据库或启动/停止 Docker，仅对 subprocess mock 执行 guard tests。

## 指纹

| 文件 | SHA256 |
|---|---|
| scripts/checks/live006_environment.py | 1c5586d8a3c2d2462f04b8bd5216591a3aadc1fdaffbd3931fc79ff84973b48b |
| scripts/checks/test_live006_environment.py | 139c81ce5469e406f42fc5fad901c61c75bd264d17bc15df3b62919253a29f49 |
| infra/compose.live006.yml | 889883cf6ff79edad7db756a2ab9d7ead34c2284b32fe0c2b93b0809479669a3 |
| docs/ai/banana-reference.md | 4cfb70957b367d9fb3c95f4cd6432e81997e793392cc140547f5df1c2819b4a7 |
| project-team/access/RESOURCE-LOCKS.md | 562b64a9145b0542a01c76afcc4dd4abcc25d06848fd0328c686e43026fedb2f |

## 亲跑和审查

`python3 -m unittest discover -s scripts/checks -p test_live006_environment.py -v`：5 tests passed，0.005s。git diff --check 通过。

固定主checkout、拒runtime重定向、拒DOCKER/COMPOSE及运行目的覆盖；仅接受本地unix Docker context。private.env要求0600且固定字段/值，不打印密码。固定15460/live006、独立compose项目和数据卷，已有容器核项目label与指定mount；没有reset/delete指令，没有MQ启动。资源登记明确ARC/QA顺序借用006数据库，MEDIA/CFG无DB依赖；005资源不触碰。

banana-reference 的原项目HEAD已独立核对为4e7c922c0e143aabbec4b9e9f835b86306952896；只读源码证实ProviderConfigSnapshot/MappingProxyType、禁止含秘密快照序列化、提交捕获与owner核验。该说明正确区分参考思路与本项目YAML实现；没有读取其私有配置。ASR协议段为目标说明，实际adapter另行审查。

## 发现

无 P0/P1。P2：private.env 读取前只核symlink/权限，未核普通文件或限制字节数；0600 FIFO会在read_text阻塞，巨大普通文件可无界读取。建议使用O_NOFOLLOW|O_NONBLOCK打开、fstat普通文件校验、固定大小上限，并添加无真实Docker调用的guard。正常private.env下目标隔离不受影响。已发ARC；最终批准需其修复或明确登记豁免。

本轮真实PG启动由ARC执行，不属于QA亲跑证据；没有验证DB可用性。最终集成验收仍须另行绑定SHA。

## P2 修复复验与批准

O_NOFOLLOW|O_NONBLOCK、fstat普通文件、8192字节上限均已实现。亲跑6项guard tests通过(0.007s)，包含FIFO与超大文件。环境范围批准，替换指纹：live006_environment.py `93dad00224967ecff8b660b0736ab11671e59fa39ab7c2522520f44ba954cedf`；test_live006_environment.py `76b682f6354318224b0195cff7c02589c6b636bc24a3faa3108a242d3adf33e9`。其余审批指纹不变。
