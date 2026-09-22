# Transkun单命令离线入口

实现scripts/run_transkun_candidate.py：本地音频→现有FFmpeg预处理→独立Python中的固定Transkun CPU适配器→原始MIDI和JSON事件。没有参考谱参数，不执行padding/补音/删音/分手/记谱。原始时间以规范化输入秒数表示，置信度和左右手没有模型证据时为null，不伪造0.99。

pipeline.json保存阶段、输入与源码/权重manifest指纹、产物指纹和失败状态；推理进程有300秒默认超时。已存在输出目录拒绝覆盖。导出前核验模型receipt实际输入/适配器/manifest/MIDI哈希与音符数量。

首次端到端暴露virtualenv Python符号链接被resolve为系统Python，丢失soundfile依赖；已改用absolute保留链接，并通过单独回归保护。失败产物transkun-entry-smoke-07-v1保留，成功v2实际运行07输出40事件，JSON事件逐项等于MIDI解析结果。API环境检查未安装torch。

18项入口与候选验证相关测试通过，含真实推理落盘验证、超时失败、输入被替换、错误计数、禁止覆盖、保留虚拟环境解释器。Ruff/编译通过。原始转录入口完成实际运行，但独立fresh代码复审未完成，记谱阶段未接入，不等同生产模型已切换。

使用方法见experiments/models/transkun/README.md新增章节；独立环境和固定模型源码仍须按前文准备，临时目录不是可发布的部署环境。
