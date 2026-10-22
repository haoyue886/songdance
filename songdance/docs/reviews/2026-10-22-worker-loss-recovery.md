# 2026-10-22 Worker强停与同任务重试恢复

基线 `bcdaaa2`。本批只运行本地隔离故障验收，不修改产品代码、依赖或生产配置，不部署、不推送、不访问供应商或原商业账本。成功运行标识 `e23d16004d`，API/Worker固定ARM64镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`，当前143应用Python文件与镜像绑定证据一致。

## 范围和时钟口径

一次性internal网络、PG16、Redis7.4、源码MinIO、正式API和RQ Worker；先一个Worker运行，强停后另建一个替代Worker，各限1 CPU、2 GiB、128进程，没有两个业务Worker同时处理。不开宿主端口或数据挂载。分析、游客/用量及reliable queue开启，付费、邮件、Creem、删除和YouTube关闭。认证仅用不可用供应商URL/不存在的本地reader占位，游客无Bearer，不测试真实身份或会话。

输入为上一批容量观测的90秒合成two-hand文件，SHA256 `da2913d1ecb727c56ffc98a06eab61e7006e85fa81da133f382cdd6daf1eb3ca`；实际HTTP只选择前30秒，遵守游客上限，不声称本轮处理了90秒。文件由既有30秒固定输入重复三次构造，不是真实完整演奏或新质量样本。

正式Worker的running outbox deadline默认仍为960秒。真实执行和SIGKILL使用正常墙钟；到期验收通过原 `dispatch_pending(..., now=...)` 参数分别传入deadline前1微秒、deadline和后1秒，没有更改数据库deadline、系统时钟或生产超时。临时目录清理则调用原 `cleanup_stale_temp_files`，分别传入该目录mtime加原86400秒TTL前1秒、后1秒。**没有实际等待16分钟或24小时，也没有验证真实定时调度延迟。** 两个局部时钟测试各自验证函数边界，不代表全系统时间推进。

## 实际结果

项目venv执行 `/tmp/notavue-worker-loss-20261022.py` 第二轮退出0；runner通过API容器内probe执行真实HTTP、PG/Redis/RQ/S3和原任务入口。两脚本及内嵌Python编译通过，没有因仅文档变更重跑无关产品全量测试。

1. API新建一个游客任务，实际RQ进入running/transcribing且execution_count=1后，仅对本轮Worker-a执行 `docker kill --signal KILL`。容器确认Running=false、ExitCode=137、OOMKilled=false；强停后DB仍running/transcribing、预占1、active1、源对象存在，不把137解释为内存耗尽或已完成任务。
2. deadline前1微秒Dispatcher处理0项，状态/账本不变；deadline时处理1项，任务failed/WORKER_LOST、outbox failed、业务预占0/消费0、active0。旧reservation恰好1 release，源对象及摘要保留、无产物，小时安全计数仍1；deadline后1秒重放处理0项，完整快照不变。
3. 用原能力token、同一个retry key发送两次真实HTTP重试，均200、仍同任务ID、attempt2，没有新任务或attempt3；2份GuestSubmission对应create/retry。新预占1、消费0、active1，小时安全计数2。
4. 在替代Worker尚未启动时，先实际获取旧attempt的PG advisory lock确认强停后锁已释放；再直接调用旧attempt的 `verify_source_job`、失败回调、quota完成入口及set_stage。失败回调对象的retries_left仅在内存置0，以覆盖重试耗尽分支，未保存或改写Redis重试字段。旧set_stage返回false，前后完整业务/账本/限流快照相同，新预占仍1；这里是显式注入迟到函数入口，不是网络自然发生的迟到投递。
5. 新建Worker-b处理attempt2，任务succeeded、5类产物成功并实际下载/解析，文件大小与SHA256核对一致；S3源字节与DB摘要相同，源摘要与强停前一致。新RQ FINISHED、execution_count=1；最终2 reservation、旧1 release、新1 consume，reserved0/consumed1、active0、安全计数2，没有双扣量。随后用受控时钟让Dispatcher将新outbox置finished，重放不再改变快照。
6. 杀进程留下的1个pipeline目录在TTL前1秒保留、后1秒删除；非匹配的保护目录及内容保留，业务/源/账本快照不变。新Worker完成后没有自己的pipeline遗留。只测原临时文件清理函数，没有借全任务过期清理删除成功任务。

旧attempt的RQ元数据在最后快照中仍为STARTED、execution_count=1；新attempt为FINISHED、execution_count=1。应用恢复依赖持久outbox到期失败和显式HTTP重试，**不宣称失联RQ注册项已自动清理、旧RQ已FINISHED或任务自动续跑**。本轮没有等待或推进RQ自身维护时钟，不验证其abandoned-job自动重试调度；临时Redis随后整体销毁。两个attempt的持久栅栏和业务账本结果按各自状态判断，不能只看旧RQ注册状态下结论。

## 收尾、失败和审查

替代Worker cgroup memory.peak为709,013,504字节，pids.peak为22，memory.events的max/oom/oom_kill均0，OOMKilled=false，正常stop退出0。被杀Worker只采集了强停前资源点，不将其读数当成完整生命周期峰值。没有用本次故障样本计算生产P95、完整恢复耗时承诺或云成本。

首轮 `960243acd5` 在probe从/tmp脚本导入app时因Python模块路径失败，尚未创建任务或执行强停。改为在/app工作目录下使用 `python -c`/runpy启动并传递phase后，用全新资源完成第二轮；首轮错误与清理回执保留在attempt-1，不标作通过。准备审查另修复游客90秒选区与合同不符、mtime纳秒转datetime精度导致TTL边界误判两项脚本问题，均在第一次运行前改为30秒选区及TTL后1秒测试，不修改生产合同或TTL。

两轮finally清理errors均为空；每轮4卷含Redis匿名卷逐名inspect确认不存在，主Agent事后只读核对两轮标签容器/网络/卷均空。无全局prune或其它项目清理。143源码绑定、原四份manifest/provenance/人工评审摘要、源输入均未修改。

执行脚本、两轮结果/日志、阶段快照、5个实际产物、资源与8卷清理回执在 `.data/notavue-worker-loss-20261022`，目录0700、文件0600，不入Git。准备独立审查核对调用路径、修复和同构runpy入口验证；最终独立复算44份归档摘要、5产物大小/摘要、143应用绑定、源输入与原四份评审摘要、权限，并交叉核对阶段快照、Worker日志和三份交付文档，未发现可行动P1/P2。审查未重跑Docker或查询已销毁数据库/Redis，运行与资源消失结论引用实际脚本、归档结果、清理及主Agent事后只读核验记录。

本批只覆盖合成30秒游客任务的一次真实SIGKILL、受控截止时钟、旧入口注入和同任务显式重试。真实960秒超时、RQ自身维护/自动重试、Redis/PG中断、多实例Worker竞争、Free/Pro账本矩阵、长时故障负载、生产内核/架构、音乐质量及云恢复仍待验；FFmpeg漏洞及既有进程隔离边界保留，不批准扩副本或上线。
