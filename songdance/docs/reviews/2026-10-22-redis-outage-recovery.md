# 2026-10-22 Redis真实中断与空队列恢复

基线 `0c3f96f`。本批只运行本地隔离验收，不修改产品代码、依赖或生产配置，不部署、不推送、不连接原商业数据库或供应商。API/Worker使用固定ARM64镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`，当前143应用Python文件与镜像绑定记录一致。

## 范围与方法

随机internal网络、一次性PG16、Redis7.4、源码MinIO及应用卷，没有宿主端口或数据挂载。正式API接收一个2秒合成A4游客任务：任务、预占和outbox持久化PG，源写入S3，原RQ ID排队成功后，不启动Worker。

随后停止本轮唯一API，直至测试结束均不重启，模拟暂停所有新准入；探针以无公开端口的短命私有容器直接读取本轮PG/Redis/S3，不能代替真实平台入口封禁。游客/用量、reliable queue和分析开启，付费、邮件、Creem、删除及YouTube关闭；无Bearer，仅不可用供应商URL/不存在本地reader配置占位，不测真实身份或认证连接。

本轮Redis显式使用 `--save '' --appendonly no`，正常stop/start会丢弃全部内存数据；这是有意构造的总丢失情形，不是生产持久化建议。Redis停止后启动正式 `python -m app.jobs.dispatch --loop`，按原30秒重发布间隔、5秒poll和退避观察QUEUE_UNAVAILABLE。没有传now、手改deadline/next_attempt_at或提前清空队列。

观察失败后停止第一个Dispatcher，防止空Redis检查与恢复竞争；再启动同一Redis容器，先确认DBSIZE=0、队列空和限流计数消失。启动第二个正式Dispatcher，按真实墙钟自然恢复原任务，确认队列精确为原RQ ID这一个元素，再启动正式Worker。所有应用连接仍使用原PG、源对象和签名配置，不建新业务任务或新attempt。

每个阶段将public表除有意变化的job_dispatches之外逐表全部行/字段排序并计算摘要；读取S3源字节对照数据库SHA256。运行时配置未修改；不将Redis限流计数丢失说成已重建，也不在计数缺失时重开准入。


## 实际结果

运行标识 `9c38d901f6`。项目venv执行 `/tmp/notavue-redis-recovery-20261022.py` 一轮退出0，两脚本及内嵌Python编译通过。没有生产代码变更，不重跑无关产品全量测试。

- 故障前：1个queued/attempt1任务，outbox published/publish_attempts1，队列恰好1个RQ ID，游客reserved1/consumed0、Redis active1/小时安全数1，源对象字节与DB摘要相同。
- 停API后、Redis停止前再取快照，27张非outbox表完整字段摘要与故障前相同。API随后始终停止；没有新HTTP准入或手动清零安全预算。
- Redis停止、正式Dispatcher启动后约32.278秒，观察到 `QUEUE_UNAVAILABLE`，publish_attempts2；任务仍queued、游客reserved1/consumed0，源字节完整且27表全字段/行数摘要不变。该时间包括循环读取/探测开销，是本机观测，不是恢复SLA。outbox在该异常分支仍名为published、带错误码，不把它说成已成功重新入队。
- 停第一个Dispatcher后，Redis重启：DBSIZE0、空队列、原RQ不存在、active0/小时数0；PG预占和27表仍保持原快照。这里主动证明运行安全计数确实丢失，没有从业务账本自动重建。
- 新Dispatcher启动后约4.946秒，原任务自然重发布，队列严格等于 `[原RQ ID]`，原attempt1不变，publish_attempts3、错误码清除。27张非outbox表与故障前相同，active/小时数仍0，不把重新排队等同限流预算恢复。
- 正式Worker执行该attempt恰1次，RQ FINISHED、业务succeeded，5类产物均成功；从本轮私有S3逐项下载并解析MIDI/时间线/MusicXML，归档字节数/SHA256一致。没有启动浏览器、HTTP下载票据或专业听感/谱面验收。唯一reservation只产生1个consume，游客reserved0/consumed1，active0、小时数仍0。
- 完成快照里outbox仍为running，等待其正常next_attempt_at（running启动后960秒）后才会由Dispatcher整理为finished；本轮没有等待这一归档点，不能声称outbox终态整理已通过。没有手改deadline或将成功任务人工置finished。RQ FINISHED、业务成功和账本单次消费已分别核对，原队列数据丢失后的应用恢复通过限定分支。

本轮只有一个已接收、尚未执行的任务。Worker在Redis恢复后才启动，不覆盖正在运行的Worker丢Redis、RQ维护/automatic retry、队列接收响应丢失、多任务并发数据丢失或生产持久化恢复；之前逻辑备份恢复及Worker强停是独立证据，不混成同一现场测试。

## 收尾、审查及运行边界

Worker内核memory.peak为667,566,080字节（636.641 MiB），pids.peak23，memory.events的max/oom/oom_kill均0，OOMKilled=false，正常stop退出0，pipeline目录为空。CPU记录是容器生命周期值，不当作模型净耗时或云成本。两个Dispatcher按本轮确切名称停止，API从暂停后未重新启动，所有短命探针均归属本轮标签。

finally无清理错误；4卷包括Redis匿名卷逐名inspect确认不存在，主Agent事后只读核对本轮标签容器/网络/卷为空。没有全局prune、其它资源清理或修改Docker全局网络配置。当前143源码、原四份manifest/provenance/人工评审摘要未变。

私有证据在 `.data/notavue-redis-recovery-20261022`，目录0700、文件0600，包含执行脚本、阶段27表摘要/源字节校验、队列和限流读数、5实际产物、API/Dispatcher/Worker日志及清理回执，不入Git。

准备独立code-reviewer修正两项脚本P2：只核对fetch预期ID而未严格比较实际队列唯一项、外层90秒超时短于finish探针150秒循环。现分别精确断言原ID和外层240秒，复核通过后才运行；没有放宽业务判据或失败重试。最终独立复算43份归档摘要，核对13份执行前快照/27表、源SHA、原RQ ID/attempt/执行次数、5类产物解析及摘要、143源码/四评审摘要、权限和清理记录，未发现遗留可行动P1/P2。基线27表仅7表非空，不外推有数据的Free/Pro历史矩阵；审查者未重跑Docker或直接查询已销毁服务，运行及清理结论依据归档脚本、结果、日志与事后只读核验。

生产Redis总丢失后必须继续暂停所有公开准入，核对正在运行任务、持久预占、全球/客户端并发和小时/日安全预算，完成适用的计数恢复/保守预算方案后才能重开。**本轮没有实现或签收安全计数重建，因此API全程保持停机。** Redis生产持久化/备份/高可用、真实平台暂停入口、Free/Pro矩阵、跨实例竞争、云RTO/RPO及音乐质量仍待验；FFmpeg和既有隔离风险保留，不批准扩副本或上线。
