# 16双谱表预览：2/4支持修复，XML一致性未通过

原meter-only候选149事件输入显式2/4/60BPM与十六分网格。首次v1因quantize._measure_units缺2/4报KeyError；已在该函数和analysis._downbeats各增加2/4=2拍，不改变自动拍号候选排序，实际2/4记谱和既有拍号测试通过。

v2可生成1part/2staff/15小节/149 MIDI事件，但仍82休止、每谱表最多3voice。该过程发生量化，起音最大变化约29.6ms、结束时间最大125ms，不可沿用meter-only的绝对秒数不变声明。候选保留源四音/教师三音冲突及误音。

独立审查发现2MEDIUM：人工指定拍号被默认confidence1、默认C major来源被误记推断；只比MIDI/timeline不够证明XML逐音一致。已修候选配置为显式0置信度占位、默认调号来源operator_display_default_not_inferred，并解释手部分配的非校准启发式性质，不改全局API字段。

新增XML读取并stripTies后的音高/起音/时值Counter与notation事件/MIDI对照。实际16 XML重构为153事件，预期/MIDI149，且部分时值改变；故v3保存failed及完整差异，不把“能解析”标为成功。该差异目前可能位于谱面聚合/延音导出或解析约定，未确认具体根因。v2不能作为三产物一致候选交付。

38相关测试通过，包含实际生成后拒绝不一致、独立相等正例及duration变更反例、2/4与既有拍号、analysis/adaptive quantization。Ruff/编译通过。本轮完成2/4崩溃修复和错误产物阻断，不代表XML一致性缺陷已修复，不生成PDF或发布包。

修正后fresh定向复审通过，前审2项MEDIUM关闭，本次0新增HIGH/MEDIUM；独立19相关测试、Ruff/编译及完整失败审计重算通过。此通过仅指元数据修正和不一致拦截，XML153/MIDI149根因仍待修复。
