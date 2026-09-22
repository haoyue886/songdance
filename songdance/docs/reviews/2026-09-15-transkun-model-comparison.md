# 钢琴专用模型第一次原始结果对照

本轮已实际运行 Transkun V2 No Pedal Extension，比较对象为 Basic Pitch 0.4.0。使用冻结的 `14-hand-crossing.wav`，两者接收同一份规范化单声道WAV；Transkun内部按上游模型配置重采样到44.1kHz。没有使用教师音高模板、量化网格、音尾删除或泛音规则调整任一模型的原始输出。

| 原始模型 | 预测事件 | 正确匹配 | 额外事件 | 漏音 | Precision | Recall | 起音F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Basic Pitch | 285 | 111 | 174 | 0 | 0.3895 | 1.0000 | 0.5606 |
| Transkun V2 | 105 | 105 | 0 | 6 | 1.0000 | 0.9459 | 0.9722 |

50ms和100ms两个起音容差的结果一致。参考MIDI原为118条事件，同刻同键合成重复折合111个可听的不同音高起音；按一对一匹配评估，不能通过重复估计一个真音获得多个正确数。该F1忽略音符结束时间，不代表时值、踏板、拍号、分手或PDF可读性已通过。

Transkun漏掉的6个音：4.5秒Eb3、11.5秒Eb3、18.5秒Eb4、25.5秒A3和Eb4、27.5秒Eb3。它们仍是待解决的漏音，不能因没有额外音而忽略。匹配上的105个音最大起音误差约13ms。

CPU实测：Transkun加载约0.168秒、推理约13.735秒；Basic Pitch本轮原始基线推理含模型加载约1秒。机器为macOS ARM64，Transkun使用CPU两线程；这不是跨硬件的性能承诺。

来源固定为 `Yujia-Yan/Transkun@c5cb8370e17b4a1650b5971ba87ee4b0d208e5b6`，源码MIT许可已核验；随包权重56,408,978字节，SHA-256 `50a80010effc2a59ffcd068a95cd2b29bd7f23a27a3515bc3ccd209c89a3d44c`。所有源码文件和配置已核对Git blob及SHA-256，推理采用 `weights_only=True` 和严格参数加载。独立商用权重/训练数据许可及真实演奏验证未完成，模型继续为离线研究候选。

结果位于 `songdance/api/tests/fixtures/audio/candidates/piano-model-comparison-14/comparison-v4.json`，包含两个容差的全部错音/漏音与匹配索引，及双方输入、原始MIDI、适配器、源码和权重指纹。Basic Pitch重新推理而非借用旧候选以证明同输入；两边失败均记录failed状态，评价器拒绝未完成任务、错误输入哈希和覆盖旧报告。

复现脚本、固定来源清单和精确环境版本位于 `songdance/api/experiments/models/transkun`。API生产环境没有安装torch，生产依赖锁、模型选择及已验证谱面未被改动；未生成评审包。

结论：本组合成练习上，钢琴专用模型显著减少了原始多余音符，但牺牲了6个起音召回。下一步需要在弱音、踏板、设备带宽和真实钢琴片段上扩大同输入对照，分别核验原始转录与最终谱面；当前证据不足以决定生产替换。

2026-09-16 复审修复：Basic Pitch receipt新增实际转录模块指纹，评价器核验全部登记的规范化音频、原始时间线和原始MIDI。代码或MIDI变化均拒绝评价。重新推理baseline-v3（含加载0.936秒），生成comparison-v4，数值与前次一致；历史报告不覆盖。相关pytest四文件31 passed，Ruff及API虚拟环境compileall通过。

下一轮输入已核对：06-sustain、07-soft、10-device的源WAV/MIDI均在本地；真实02-brahms-intermezzo片段SHA-256与human-provenance记录一致，许可记录为Public domain。下一轮需将实验脚本参数化并保留第14条回归，再运行四个样本。真实片段没有已核验的逐音参考，不能套用合成集F1；先交付原始对照和待听审差异。

修复后fresh独立Stage 1/2复审通过，0 HIGH/0 MEDIUM；审查者重跑14项专项测试、Ruff和编译，重算v4完整报告一致。本轮离线对照已闭环，不等同于整项目或生产准入通过。
