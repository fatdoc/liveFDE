# LIVE-006C LOCAL 8521c0c 独立审查

独立QA /root/qa_live001，2026-10-06；固定8521c0cd1cbf43a8f4b26085af3977d1e7927767源码副本qa-local/snapshot。未加载真实模型、下载权重或访问云。15单测通过79.30秒；作者真实冷/暖/stream证据文件存在，QA仅审阅，不声称本轮亲自执行模型smoke。

## P1：已检测语音的空转写被误报为完整

observations.analyze_audio在VAD返回有效语音区间后，Nano raw为空或text空时continue；provider._result无条件complete=True。独立轻量fake model探针输出：VAD1000ms，ASR[]，segments0，complete=True。混合场次中的空片段也会静默丢失且标完整。

请区分VAD确实无语音与VAD有语音但ASR无结果；后者应显式失败或带缺失信息complete=False，不能当作已完整识别。需覆盖全空与正常+空混合片段。已交ARC转作者，当前LOCAL暂不批准。

## 其余审阅边界

静态看到推理使用显式本地路径/model_conf绕过hub；下载仅独立provision入口；native线程取消使用shield等待，再释放model_lease，缓存空闲卸载与跨进程文件锁明确。speaker短段null、vad_window与vad来源区分、未声称词级对齐；情绪分数是模型分类值。运行许可与单样本CER边界在作者报告明确。真实native取消与IPC最终组合仍待验，不以15单测替代真实推理。

## 修复复审：模块批准

f05bcd2cc42694bf486555c2506341ae6d025565 基于8521c0c的差异只修改VAD/空ASR/过短语音区间校验与测试/文档；独立21项测试通过2.74秒，0skip。原probe现有语音空输出抛local_asr_empty_for_speech；VAD显式value=[]仍合法0observations。全空和混合正常+空结果均不再报告complete成功。

批准8521c0c+f05bcd2模块集成，P1关闭。既有真实模型smoke保留为正常输入路径作者证据，没有重复加载权重，不冒称新缺失输出边界做过真实模型实验。最终native worker/文件/WS端到端仍待验。

非阻塞提示：IPC safe_code应加入新增LOCAL校验错误码，否则客户端仅得到worker_failed；这不使结果假成功或自动云fallback，但影响排障可读性。已告知ARC。
