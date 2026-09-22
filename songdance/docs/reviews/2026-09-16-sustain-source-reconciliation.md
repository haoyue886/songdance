# 06源版本核对与MuseScore尝试记录

旧generated/06-sustain.mid含60事件，每2秒一簇，前三簇为C3/G3/C4/E4、F2/A3/C4/F4、G2/G3/B3/D4，均4音。此前Transkun候选和发给老师的06原音频来自此旧版本，不能用它宣称验证了老师要求的恰好三音513/614/572。

项目已存在sustain-triad-v2-manifest.json，定义G3/C4/E4、A3/C4/F4、G3/B3/D4，但本次检查时其预期目录内truth.mid不存在。新脚本prepare_sustain_review_source.py按该合同生成独立06-teacher-triad-source-v1，30秒/15簇/45音。2秒间隔和1.6秒时值是现有合成合同参数，不是本轮老师的新听审结论。此源明确标记new_synthetic_teacher_pattern_not_original_audio，尚未转录，不覆盖原音频或以前的指标。

脚本拒绝覆盖，校验和弦合同，保存失败状态和代码/合同/音频/MIDI指纹。运行源码快照executed-generator.py匹配receipt.script_sha256；此后只调整长字符串排版。5项相关测试、Ruff和编译通过。尚未完成fresh独立复审，不将新源或新谱面标通过。

## MuseScore实际尝试

通过原生界面打开统一候选07及独立临时副本，文件选择框能选中目标文件，但点击打开后活动窗口仍为原candidate.musicxml，显示旧06片段，未观察到新乐谱渲染。因此不能标记07/10的MuseScore导入通过，也不能宣称出现了新的XML导入错误。未保存或关闭用户已有未保存乐谱。此UI验证仍未完成；不再通过仅music21解析绕过该门禁。
