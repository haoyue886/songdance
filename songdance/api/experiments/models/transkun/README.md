# Transkun V2 CPU 离线对照

本目录只用于研究评估，不进入生产 Worker 或 API 依赖锁，不替换 Basic Pitch，也不生成统一评审包。

## 已固定来源

- 仓库：<https://github.com/Yujia-Yan/Transkun>
- 提交：`c5cb8370e17b4a1650b5971ba87ee4b0d208e5b6`
- 源码许可：该提交的 `LICENSE` 为 MIT。
- 权重：仓库随附 `transkun/pretrained/2.0.pt`，56,408,978 字节。
- 权重 SHA-256：`50a80010effc2a59ffcd068a95cd2b29bd7f23a27a3515bc3ccd209c89a3d44c`。
- 官方README称默认权重为 V2 No Pedal Extension，使用数据增强；默认CPU、44.1kHz、16秒窗口/8秒步长。
- 这里只核验源码许可和随仓库权重来源。独立商用权重条款、MAESTRO训练数据相关要求及真实录音质量仍需单独核验，`production_eligible=false`。

完整源码、配置、许可文件和权重哈希见 `source_manifest.json`。下载及验证文件在独立临时目录，未把模型文件提交到项目。

## 重现步骤

1. 用 GitHub CLI 下载上述提交的 tarball 和 recursive Git tree，保存到临时目录。
2. 使用项目Python运行 `verify_source.py --archive <tarball> --tree <tree.json> --output <source> --manifest <new-manifest.json>`，每个文件必须匹配远端固定Git blob，之后再导入代码。
3. 创建独立Python 3.11虚拟环境，安装CPU PyTorch 2.5.1、torchaudio 2.5.1和记录的运行依赖；不要安装到生产API环境。
4. 在API环境运行 `python -m scripts.prepare_piano_model_input`，重新规范化第14条音频、推理Basic Pitch原始事件，并保存输入和产物哈希。
5. 用独立环境运行 `run_cpu.py --source-root <source> --manifest source_manifest.json --audio <basic-output/normalized.wav> --output <empty-transkun-output>`。使用 `weights_only=True`、严格参数加载、CPU推理，只做模型所需的44.1kHz重采样；不套用教师音高模板或记谱后处理。
6. 在API环境运行 `python -m scripts.compare_piano_model_outputs --transkun-output <transkun-output> --report <new-report.json>`，比较原始事件50ms/100ms起音匹配。报告不能覆盖旧文件。

Basic Pitch与Transkun都必须记录同一normalized WAV的SHA-256。比较参考将同刻同键的源重复MIDI事件计为一个可听音高起音，保留118条源事件和111个不同起音两个计数。模型原始音符不量化、不裁切、不按参考筛选。失败推理会写 `status=failed`，不会被评价脚本当作成功结果。

本阶段只评价一个合成回归片段；即使指标提高，也不能据此声称真实钢琴录音质量已通过或决定生产换模。

## 本次实际运行

macOS ARM64、Python 3.11.12、CPU两线程。PyTorch轮子从官方备用源下载，SHA-256为 `31f8c39660962f9ae4eeec995e3049b5492eb7360dd4f07377658ef4d728fa4c`。为避免低速重复下载，数值库以现有API已安装版本的文件副本放入独立环境；没有共享可写环境或修改API依赖，完整版本记录在 `requirements.lock`。

适配器直接读取固定配置JSON并构造上游 `ModelConfig`，所有权重键严格匹配，不需要moduleconf动态加载；锁文件仍记录了环境准备时安装但未使用的moduleconf。源码、权重和第三方运行库在临时目录，结果与receipt在独立候选目录。

正式对照报告为 `tests/fixtures/audio/candidates/piano-model-comparison-14/comparison-v4.json`。Basic Pitch基线是本轮重新推理的 `basic-pitch-v3`，Transkun为 `transkun`；两者输入SHA-256均为 `c73a42191758d452c9a65c60130b0113d7d1e3e475b2f536d891da5a24f5886d`。50ms与100ms起音容差下结果一致：Basic Pitch 285事件/111匹配/174额外/0漏音，Transkun 105事件/105匹配/0额外/6漏音。

Transkun权重加载约0.168秒，30秒音频CPU推理约13.735秒。本次只比较原始音高与起音，尚未评价键盘释放、踏板、分手、拍号与谱面，因此不是最终曲谱质量结论。

## 扩大样本对照（2026-09-16）

准备和评价入口现支持 `--case-id`：`06-sustain`、`07-soft`、`10-device`、`14-hand-crossing`、`02-brahms-intermezzo`。默认新输出目录为 `tests/fixtures/audio/candidates/piano-model-comparison-expanded-v1/<case-id>/basic-pitch`。旧v4保留历史代码指纹，不能用修改后的脚本伪装原版本重建；第14条在新目录重新推理验证。

在API目录，依次执行（输出目录须为新目录）：

```sh
.venv/bin/python -m scripts.prepare_piano_model_input --case-id 06-sustain --output <new-case-dir>/basic-pitch
<isolated-python> experiments/models/transkun/run_cpu.py --source-root <verified-source> --manifest experiments/models/transkun/source_manifest.json --audio <new-case-dir>/basic-pitch/normalized.wav --output <new-case-dir>/transkun
.venv/bin/python -m scripts.compare_piano_model_outputs --case-id 06-sustain --baseline <new-case-dir>/basic-pitch --transkun-output <new-case-dir>/transkun --report <new-case-dir>/comparison.json
```

替换case-id可运行其他样本。真实片段必须匹配已有`human-provenance.json`中的SHA-256和允许的许可记录；不读取其他样本的MIDI作为参考。报告的`basic_pitch_raw`、`transkun_raw`与参考计数均为null，仅`unscored_model_differences`列出同音高起音交集及双方独有事件。这些是听审线索，不是准确率或错误数。两模型原始MIDI及时间线始终保留，不经过记谱模板、删音或量化。

## 单命令原始转录入口

在API目录执行：

```sh
.venv/bin/python -m scripts.run_transkun_candidate --audio <local-audio> --output <new-output-directory> --python <isolated-environment/bin/python> --source-root <verified-transkun-source>
```

支持预处理后最长90秒的单声道输入；默认推理超时300秒，可用`--timeout`调整。入口自动规范化音频，调用固定验证过的CPU适配器，在`model/raw.mid`保留原MIDI，并导出`raw-timeline.json`和`pipeline.json`。没有padding、节奏量化、自动分手、模型融合或参考谱模板。时间线`confidence`与`hand`明确为null，因为原始MIDI不提供这些判断。

整个入口不会导入torch，重依赖只在指定的独立Python进程中加载。虚拟环境Python路径保持符号链接，不解析成系统Python，以免丢失虚拟环境依赖。源码和权重仍按source_manifest核验；输出目录须不存在，错误和超时保留日志及失败阶段。所有结果为非生产研究候选，不能直接代表谱面通过。

## 显式单旋律记谱阶段

确认输入是单高音旋律后，使用上一阶段输出目录：

```sh
.venv/bin/python -m scripts.notate_transkun_candidate --input <raw-output-directory> --output <new-notation-directory> --tempo 120 --meter 4/4 --profile confirmed-monophonic
```

`--tempo`与`--meter`由操作者明确选择，不声称自动检测；例中的120/4/4用于复现现有07候选。此路径拒绝低音、同刻多音与密集起音，不能用于06/10/14。只在单旋律上下文截断音尾，导出MusicXML、记谱MIDI、timeline及notation审计；所有起音量化位移、原结束与截断结束保留。

原始推理事件保持不变。置信度字段仍为null，谱表手部分配来自显式配置，不冒充模型推断。现有score API内部所需数值confidence使用0占位，对外不作概率声明。新输出不继承别的版本教师评级，未替换生产路由。
