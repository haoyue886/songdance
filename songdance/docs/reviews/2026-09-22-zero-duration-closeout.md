# 同刻音零时值修复收尾

## 已修复

`_cap_eighth_note_durations` 原实现取排序后的下一个事件起音作结束上限；同刻多音时第一个音会变成start=end。新实现取下一严格更晚起音，同刻所有事件保留，短音不延长，无后续起音时仍使用半拍上限。不合并近同时音、不删泛音，不承诺每个非末尾音最多半拍。

独立限定审查Stage1/2通过，未发现新增HIGH/MEDIUM。已追加乱序输入/长间隔和1e-10秒近同时起音的持久回归，明确近同时容差不属于此修复范围。

## 实际08结果

原始Basic Pitch仍111事件，原MIDI未变。0922拍格校准后的旧候选92记谱事件，新正时值候选94；100ms起音评价新53匹配/41额外/6未匹配，正确匹配未减少，但这不是误音改善。更多事件被保留是零时值不能再隐性丢弃音符，不能据此宣称音质通过。

原始旧版90→校准后92的净变化包含MIDI84增加2、MIDI62增加1、MIDI100减少1，不是简单新增两个模型识别事件。量化后槽位筛选与时值截断共同影响结果，现有泛音与多义槽仍未解决。

## 本次最终验证

2026-09-22执行11个相关测试文件，189 passed，40.48秒，包含OSMD浏览器、single staff、score validation、voicing、quantization、melody cleanup、crossing、transcription service和pipeline。日志`/tmp/songdance-zero-duration-closeout.log`。新增测试Ruff、score.py与测试编译、git diff --check通过。

仅关闭零时值缺陷。已接受06/07/10候选未覆盖，生产模型仍Basic Pitch，未部署。最新score.py改变会使依赖旧代码的报告指纹失效，189项相关通过不是全量绿色声明；正式复评、08/14误音质量问题与受影响历史证据刷新仍须分别处理。
