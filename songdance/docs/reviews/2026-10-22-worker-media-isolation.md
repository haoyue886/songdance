# 2026-10-22 Worker 音频规范化接入文件与网络限制

基线 `9d78b2a`。本批把 `app.pipeline.audio.preprocess_audio` 接入已有 `run_media`，不增加依赖、修改音频算法参数、业务账本或生产开关，不部署、不推送。上传和 Worker 的普通 FFmpeg 调用现均使用该包装器；yt-dlp 的联网下载及其派生 FFmpeg 仍单独保留，YouTube 生产开关继续关闭。

## 变化

Worker 的来源是上传裁剪或 YouTube 转换后持久化的 `source.wav`，现在只允许 WAV/file 输入，解码、编码及滤镜各使用一个线程。输出仍为 22,050 Hz、单声道、16-bit PCM，响度滤镜仍是 `loudnorm=I=-16:LRA=11:TP=-1.5`。

正常化调用复用上一批精确输入/输出 Landlock 规则、socket/元数据 seccomp 限制、无应用凭据环境及进程资源限制。Linux ABI 不足或安装策略失败时仍失败关闭。输出在目标父目录的新私有临时目录中生成，成功且文件大于44字节才由父进程原子替换目标；原调用者的重复输出能力保留，失败不破坏旧结果，临时目录自动清理。

墙钟超时仍报告 `AUDIO_PREPROCESS_TIMEOUT`；隔离设置、进程失败、异常输出及文件错误映射为 `AUDIO_PREPROCESS_FAILED`。Worker 遇到策略失败会在 preprocessing 阶段结束，不进入模型或发布产物。

## 宿主回归与音频一致性

- 在仓库根执行项目 venv 的 `pytest -q -p no:cacheprovider`，范围为 `test_pipeline.py`、`test_transcription_service.py`、`test_audio_preprocessing_security.py`、`test_durable_jobs.py`、`test_phase6.py`、`test_jobs.py`、`test_long_audio_probe.py`、`test_usage_ledger.py`、`test_guest_usage.py`：**148 passed、2 skipped**。跳过的是 macOS 上两个 Linux-only 隔离测试；不标为宿主执行了内核限制。
- 新增/调整测试覆盖包装器白名单传参、90秒片段、原命令PCM一致、策略拒绝/超时/解析失败/无效输出时保留旧目标和清理半成品、Worker不进入模型。Ruff check/format、`git diff --check` 通过。
- 另从基线 `9d78b2a` 读取原规范化函数，在私有临时目录对全部16个合成固定案例和10个人工评审录音案例作新旧对照，**26/26 的 WAV 参数和 PCM 字节完全一致**；输入SHA256前后相同。没有运行重置人工意见的脚本，没有重写旧报告或重新签收既有音乐质量/指纹门槛。源代码指纹改变后仍须按原评审流程判断有效性，不以PCM一致自动批准历史质量证据。

## Linux ARM64 与真实 RQ

用仓库 Dockerfile 和既有本机代理作为临时 build 参数构建 `notavue-api:worker-media-9d78b2a`，Docker 摘要 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`。143个应用源码文件与仓库逐字一致。系统/依赖层复用上一批，未新增依赖或重扫漏洞。

在 `network=none`、2 CPU、2 GiB、128进程上限、无宿主挂载的临时容器，直接执行仓库抽取的普通WAV、90秒PCM对照及Worker Linux权限用例，三项通过。当前输入读取和指定输出写入正常；系统文件读取、UDP socket创建及兄弟任务文件chmod均拒绝。90秒新旧对照整体约3.8秒，子进程观测最大RSS为100,284 KiB、累计CPU约4.1秒；该数含旧参考命令和其他检查，不是生产推理或并发容量指标。

随后以固定同摘要镜像运行生产 `python -m app.worker`，在随机 internal network、一次性 PostgreSQL/Redis/源码MinIO和临时密码中完成真实队列任务：

- API 上传2秒合成A4 → Redis入队 → RQ Worker执行 → 受限规范化 → ONNX推理 → 记谱 → S3持久化，约15秒后 succeeded，5类产物（raw_midi/raw_timeline/midi/musicxml/timeline）均成功。
- Worker 使用2 CPU、2 GiB内存、128进程上限，未发生OOM；任务结束后pipeline临时目录为空，SIGTERM退出0。任务后 `docker stats` 约49.55 MiB是空闲读数，不能作为任务峰值。
- 同轮PG迁移014、空users、health200、Redis PONG、S3字节往返/精确multipart中止和同前缀保护、cleanup通过。finally清理无错误，事后本轮标签容器/网络/卷均空。

上述真实任务只使用本地合成输入和隔离服务，认证、计费、邮件、YouTube及分析开关均关闭。没有访问供应商、正式数据库、云存储或原业务账户。

## 审查与边界

独立 code-reviewer 已追踪上传/YouTube WAV来源、Worker attempt持久化、临时文件及失败路径，并独立执行规范化/Worker定向9项、既有媒体安全26项通过（1 Linux-only跳过）。最终复核重新计算143个应用文件及26个固定输入SHA256，确认PCM对照脚本比较完整数据、RQ脚本使用真实Worker入口、测试/运行/清理证据与记录一致；未发现本批遗留可行动P0/P1/P2。审查者未重演Docker或联网，容器实测由主Agent执行并留证。

私有证据在 `.data/notavue-worker-media-20261022`，含构建/测试日志、Linux结果、26例PCM对照、真实RQ结果、资源配置及清理结果，不入Git。本批只验收一次小任务和90秒规范化，不签收90秒完整推理、并发吞吐或成本容量。仍共享UID，保留同UID信号/调度控制、恶意后代脱离原进程组、聚合CPU/内存等上批边界。FFmpeg CVE仍未修复，yt-dlp独立调用、目标amd64/生产内核、真实云恢复及音乐质量门槛仍待验，不能据此上线。
