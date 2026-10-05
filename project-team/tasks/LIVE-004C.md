# LIVE-004C 材料上传、关联与授权读取
- owner BE-02（本轮执行子任务 /root/eng_live002）；reviewer 独立QA/ARC；状态 done。
- base da128af；branch feat/LIVE-004C-materials；工作副本 .worktrees/live-004c-be。
- 独占 services/backend/src/live_review/modules/materials/、integrations/storage/、migrations/versions/0003_materials.py、tests/test_materials.py、tests/materials_fixture.py、本卡、reports/LIVE-004C/。
- 共享依赖A身份996b4f4与B场次d76009e已按ARC授权引入，仅依赖并非批准；B场次0002已引入，C0003串行。不改main/core/config/锁，由ARC接线。
- DB/runtime：runtime/live-004/4c.env；PG15440 live004_4c；storage-4c；不操作5432/15432/5188。
- 验收：持久幂等init、流式PUT大小/租约、实际格式/哈希finalize、DB失败可恢复、不可覆写、同hash去重可跨场次关联；权限先于Range/ETag/size；GET/HEAD、206/416/400、If-Range与多range200；PDF仅reference；真格式合成fixture/真PG、重启原字节。
- 限制：无远程URL抓取、无ASR、无上传续传、无自动清理原材料；租约失效以token隔离，旧任务不覆盖新blob。
- 回滚：代码revert，迁移downgrade仅在该任务测试DB显式验证；禁止清用户卷/原材料。
- 交付：提交SHA及独立结论由后续报告记录，不自批/不合并main。

- 本轮集成：A f34319f、B e1c4cb8、C2541817及修复213870d；真实全套32通过/0skip，综合HTTP与增量迁移通过。独立review见对应reports，PM最终产品验收通过。

- 最终代码集成：a9a15d2f3d96cedb38b0a476e847dad3dfa0c996；独立批准树d3f6af1bcafb2f27d1a6251fd6e4832707d0e84c与提交树一致。PM-01（01a10b7c-30e0-7fa3-9545-0001d85a33b3）最终验收通过，仅身份/场次/材料后端；见reports/LIVE-004/final-review.md及change.md。
