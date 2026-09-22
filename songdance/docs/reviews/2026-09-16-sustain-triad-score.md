# 06新三音源候选谱v2

消费missing-notes-v2中的45个模型/音频建议事件，核验候选MIDI哈希后按80ms起音簇分组。每组必须恰好3个不同音高，否则拒绝；没有读取或替换为513/614/572参考音高。

记谱展示假设为60四分音符BPM、4/4、每和弦二分音符（2秒）。所有事件距离拟定网格须<=50ms，逐音记录before/after，不声称已从音频识别出这个唯一拍号/速度或被老师确认。共15和弦，7个完整小节+末尾半小节，总时长30秒，单高音谱表，不推断踏板。

music21首次导出v1自动补出末尾二分休止符，把谱面延至32秒，故v1不交付。v2仅删除经验证的末尾自动二分休止，并将最后小节设为implicit=yes；所有有音高事件原样保留。不能把“不完整小节”当非法时值，也不靠补空白假装完整片段。

v2输出45音/15和弦/1staff/0休止符/0小节错误/1末尾不完整小节。MusicXML与MIDI均为同样45音和起音组，MIDI结束30秒；timeline记录记谱假设、时值变化、来源/输出指纹、production_eligible=false与MuseScore not_run。

产物位于api/tests/fixtures/audio/candidates/06-teacher-triad-score-v2，含score.musicxml、score.mid和timeline.json。应搭配06-teacher-triad-source-v1/source.wav听审，这是新三音合成源，不是旧四音录音的修正版。

24项相关测试通过，涵盖非模板音高不替换、缺音/多音/重复音/偏移拒绝、实际XML/MIDI/审计一致性和先前音频建议反例；Ruff/compileall/xmllint通过。MuseScore实际导入、fresh独立审查和教师复评仍未完成，不标完整通过，不替换生产。
