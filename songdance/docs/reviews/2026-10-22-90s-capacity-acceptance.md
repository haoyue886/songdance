# 2026-10-22 90秒完整推理与双Worker本地容量观测

基线 `63c097e`。本批没有修改生产代码、模型阈值、依赖或生产限额，只在新建本地私网中验证现有90秒处理链与两个受限Worker同时运行。未部署、推送、发信、调用供应商或连接原业务数据库。以下是三次合成输入的实测，不能签收生产P95、专业音乐质量或5/10分钟能力。

## 输入、环境与验收方法

固定API/Worker镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`，linux/arm64，应用源码与基线一致（上一批143文件核验）。宿主Colima提供4 CPU、约7.74 GiB内存。使用正式API入口、RQ Worker、ONNX、结构分析、记谱和S3适配器；新建随机internal网络、一次性PostgreSQL16/Redis/源码MinIO卷和临时密码，没有宿主端口或数据目录挂载。

输入来自固定合成集 `05-two-hand`、`16-noisy-polyphony`，各将完整30秒PCM重复三次构成90秒WAV；来源与新文件SHA256留存，原固定素材未改。两种输入用于资源和区间运输观测，不冒称真实完整演奏、已通过质量评审的新固定集或人工听感验收。音符覆盖检查下载并解析raw/clean时间线和MIDI，检查三个30秒窗口均有音符且末段到85秒以后；它排除只处理前30秒等截断，不证明每个音符识别正确或覆盖质量。

结构分析开启，认证、用量、Creem、邮件、YouTube和可靠派发开关关闭，沿用原legacy上传→Redis→RQ真实链。仅隔离测试配置将global active设为2，client active仍为1；API只信任127.0.0.1这一测试代理，三组RFC5737合成IP用于验证独立客户端与全局背压，不修改生产代理或限额。

执行 `songdance/api/.venv/bin/python /tmp/notavue-capacity-20261022.py` 退出0。先运行一个2 CPU/2 GiB/128进程Worker；结束并正常停止后，运行两个各1 CPU/2 GiB/128进程Worker，总Worker CPU预算仍为2、内存硬上限合计4 GiB。每阶段均为新Worker容器。父runner约每2秒加探测耗时采集cgroup内核memory.peak、memory.events、cpu.stat、pids.peak及API `/health`，结束时额外采集一次。没有通过放宽解析器限制、关闭分析或换静音样本制造通过。

## 实测结果

| 阶段 | 90秒输入 | 提交到终态 | Worker内核内存峰值 | 结果 |
| --- | --- | ---: | ---: | --- |
| 单Worker，2 CPU | two-hand | 32.808秒 | 798.82 MiB | succeeded，5类产物成功 |
| 双Worker，各1 CPU | two-hand | 38.799秒 | 两Worker分别800.96/790.32 MiB | succeeded，5类产物成功 |
| 双Worker，各1 CPU | noisy-polyphony | 38.828秒 | 同上，共两Worker | succeeded，5类产物成功 |

三个任务均使用新加载的Worker子进程，但没有清空宿主或VM文件缓存，不代表完整冷启动；所有任务的raw/clean MIDI及时间线均含末段约89.40秒的音符，三个30秒窗口都非空。two-hand的原始680音符、清理611音符在单/双Worker下相同；noisy-polyphony为453音符。MusicXML的既有服务端解析状态passed、structure_errors为空，但没有OSMD/谱面专业复评，不能将可解析当作质量通过。

分析报告的duration_seconds均为90，耗时11.51/12.72/12.70秒，无超时/失败原因；状态为 `analyzed_with_defaults`，包含 `KEY_SIGNATURE_LEADING_TONE_ABSENT` 等既有证据降级提示，不宣称所有调性判断可靠。每个任务从admission到终态的本地耗时均低于规范360秒目标，但只有一次单任务与一轮双任务，**不计算或批准任务生产P95**，也没有验证重试/失败率或真实曲目分布。

双任务的transcribing状态有重叠，两容器真实Worker日志也分别记录成功。第三个不同测试客户端请求在前两任务尚未完成时返回429、`GLOBAL_CAPACITY`、`Retry-After: 60`，路径在创建任务/解析媒体前拒绝。基线成功后，同一测试IP能再次提交并发阶段任务，说明该基线占用已释放；并发阶段结束后的空Redis active集合未另行读取，不额外声称已逐键验证。每客户端1个active限制保持，生产副本数没有变为2。

## 资源与健康检查的含义

- memory.peak是内核累计容器峰值，不是空闲RSS。单Worker峰值837,627,904字节；双Worker分别839,864,320/828,715,008字节，峰值之和约1.554 GiB是上界估计，不能称同一时刻聚合峰值。非原子顺序采样的memory.current之和最大约1.344 GiB，也不当成严格同时的峰值。
- 所有Worker的memory.events中max/oom/oom_kill均为0，容器OOMKilled=false，PID峰值28/28/27，低于128。容器级上限包括RQ父进程、模型子进程和媒体子进程；同UID信号、后代行为等上一批隔离边界继续保留，不能外推所有恶意输入都安全。
- 单Worker累计CPU约35.85 core-seconds，双Worker各约37.44/37.31 core-seconds，包含启动和周期观测开销，不能当作精确模型耗时或生产账单；没有取得目标云价目及成本预算，本批不计算美元成本或确认Pro价格。
- 单/双阶段各15/16次 `/health` 均200，样本最大33.98/14.63毫秒。测量是容器内loopback请求，排除Docker启动探针的成本，不含公网、TLS、BFF和真实用户延迟；31个健康样本不替代生产API P95。
- 最后Worker正常SIGTERM退出0，pipeline临时目录在单任务后为空；所有自建容器、网络和卷finally删除，按本轮标签查询均为空。没有更改用户Docker状态或清理其它项目资源。

## 审查、留证与未验收项

准备独立审查发现runner复制结果失败时可能复用旧JSON的P2；执行前已修为每阶段删除旧结果、复制失败不读旧文件、复制回执及成功结果绑定本轮 `run_id=336a62f41d`，并增加最后一次cgroup采样。独立替身复现确认旧结果会被拒绝，编译通过。最终code-reviewer独立重算任务耗时、产物和覆盖、分析时长、内存/CPU/PID与OOM、health和429数字，核对运行标识、三遍PCM和143源码指纹，确认三文件记录及链接一致，未发现本批新增可行动P1/P2。审查未重演Docker或联网，实际停服/清理依据主Agent执行、runner断言与回执。

原始输入证明、客户端状态历史、下载解析摘要、cgroup采样、Worker日志、容器资源配置、退出/清理证明及脚本私密保存在 `.data/notavue-capacity-20261022`，不入Git。结果没有把进程退出0等同容量门禁，三个任务均逐项核对产物和覆盖字段。

本批只完成ARM64、三次90秒合成输入的受限观测。目标amd64/生产内核、持续压力、更多真实曲目、错误/重试风暴、可靠派发/账本并发、聚合成本及专业音乐质量仍未验收。yt-dlp尚未接入同一媒体限制，FFmpeg CVE仍未修复；不增加生产副本、调高生产限额或批准上线。
