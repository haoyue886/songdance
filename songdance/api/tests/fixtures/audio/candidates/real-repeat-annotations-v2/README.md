# 真人重复音标注草稿

这不是最终评审包。候选来自模型，不能当作正确音符；这是偏置检索集，不代表整段录音。
每个WAV保留原音频PCM，manifest列出起止采样点、模型音高、候选在片段内的位置。

请逐片听辨模型候选处是否真的再次击键，填写labels.json：
- reviewer：填写实际复核人的姓名或稳定代号，不要填写模型名称。
- judgment：restrike（确有再次击键）、no_restrike（没有再次击键）或uncertain（无法判定）。
- restrike必须填写confirmed_pitch（MIDI整数21–108）及confirmed_onset_sec。
- confirmed_onset_sec以原30秒录音片段开头为0，不能填写短WAV内的时间。
  两者差为start_sample/sample_rate。
- no_restrike和uncertain保持两个confirmed字段为null；
  no_restrike只否定再次击键，不证明应删音或属于泛音。
- 每条notes写判断依据或疑问；不确定就保留uncertain，不能猜测。

全部pending/uncertain解决前验证不会通过。即使验证通过，也仅表示人工表单完整，不能自动授权删音或声称全曲准确率。
