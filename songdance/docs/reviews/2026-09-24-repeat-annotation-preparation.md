# 真人重复音标注准备

新增prepare_repeat_annotations/validate_repeat_annotations两个离线入口。从已绑定02-brahms真人源中检索同音前驱间隔0.1–1.2秒的120候选，源PCM短片逐采样保留，原音频/原MIDI/来源/时间映射记录在manifest。模型候选不是真值，是有偏检索集，不能计算整段召回率。

当前草稿目录 `tests/fixtures/audio/candidates/real-repeat-annotations-v2` 包含README、manifest、全pending的labels和120个WAV。v1保留早期说明稿。没有代填姓名、评级或真实音高，没有最终ZIP或曲谱评审包。

验证器核对源绑定、复算候选身份、采样率与起止位置、片段PCM和哈希，检查标注身份完整/人工复核者非空/判断及文字依据。restrike要求钢琴范围MIDI音高和原30秒片段内的有限起音时间；pending/uncertain拒绝通过。no_restrike只否定候选再次击键，不授权删除持续音。通过状态明确为complete_human_form_only，不能验证填写者是否真实听辨，更不保证音乐真值。

独立审查指出最初validator只比较manifest自报片段哈希，无法防止联合改写时间映射与清单。现已补源PCM逐样本比对和映射复算，并补改后重绑manifest的反例。

实际待办为人工逐片听辨，不能由模型自动填写后当作独立人评。此轮仅准备可执行标注材料；16额外29音仍未修复，不接入生产。

主相关13测试通过（5.74秒），Ruff与编译通过。fresh两阶段独立复审0HIGH/0MEDIUM，独立6测试通过（1.70秒），复算120片段及联合篡改反例通过。持久化v2仍全部pending，本轮没有获得人工标注。
