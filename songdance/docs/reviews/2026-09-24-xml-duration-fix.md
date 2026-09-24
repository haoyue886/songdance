# XML和弦时值一致性修复

根因：populate_part使用默认group_harmony，允许同起音音符的结束差1个量化单位，组成和弦后统一取最大结束；MIDI仍按独立事件长度输出。最小反例C4持续1.75秒、E4持续2秒，旧XML将短音延长。16 v3此前XML stripTies读153个事件，对比MIDI/notation149，含时值差异。

最小修复：仅谱面构造的分组调用显式HarmonyConfig(duration_tolerance_units=0)，不同结束的同时音保持独立；和声分析默认tolerance=1不改。不会按参考删音、补三和弦或修改模型。

16 v4实际XML合并延音后149/MIDI149/notation149，音高/起点/时值Counter全部相同；两个staff、9个和弦、101休止、小节时值错误0。比v2的82休止增加，说明正确保存独立长度会暴露更多织体复杂性，不能据技术一致声称可读性或音质已通过。原149个模型pitch多重集合保留，配置仍是2/4、60BPM、十六分量化假设。

v4在api/tests/fixtures/audio/candidates/16-score-preview-v4；旧v1失败、v2不一致、v3失败均保留。未自动替换已确认样本或生成最终ZIP。

117项相关测试通过，29.14秒，包括OSMD、score validation、声部、单谱表、持续音压缩、08/13相关、真实转录服务；Ruff/compileall/xmllint/diff通过。独立审查实际回读149一致及三产物SHA，最小反例恢复旧规则会失败，默认和声配置仍1。独立环境OSMD Chrome启动EPERM未加载谱面，主agent解除沙箱的117测试覆盖通过。

fresh限定两阶段审查最终0HIGH/0MEDIUM，可关闭本轮和弦分组延长短音造成的XML不一致缺陷；v4仍待评审。301行既有文件大小提醒作为LOW保留，本轮不扩大重构。
