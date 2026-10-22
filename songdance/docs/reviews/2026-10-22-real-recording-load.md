# 2026-10-22 真实钢琴录音双 Worker 有界连续负载

基线 `37e6e5a`。本批仅运行本地隔离验收并记录结果，不修改产品代码、依赖或生产配置，不部署、不推送、不连接供应商或原商业账本。运行标识 `86bdd11f3d`，API/Worker固定ARM64镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`；当前143应用Python文件与镜像绑定证据逐项一致。

## 输入和运行范围

完整使用现有 `human-manifest.json` 的10段真实演奏录音：巴赫、勃拉姆斯、莫扎特、拉赫玛尼诺夫、肖邦和斯克里亚宾片段，覆盖复调、快速、弱音、踏板、双手及房间噪声。每段约30秒（巴赫29.9922秒，仍在既有0.01秒容差内），按既有 `human-provenance.json` 校验源SHA256、Public domain或CC BY-SA 3.0许可记录，没有新下载或重新裁剪。许可/作者/源页元数据随私有输入证明保留。没有将重复、拼接片段称作90秒完整真实演奏。

每段跑2次，共20个新游客任务，两个客户端闭环：每lane提交一个任务，等对应attempt的RQ FINISHED、下载并核验产物后，再提交下一个。第二lane从第6段开始错开样本顺序。这里是固定数量的连续负载，不是按固定到达率的开放压测、长时间soak或生产流量分布。

一次性internal网络、PostgreSQL16、Redis7.4和源码MinIO；两个正式 `python -m app.worker` 各1 CPU、2 GiB、128进程，global active=2、client active=1。无宿主端口或数据挂载；输入用docker cp放入临时API容器。开启分析、游客/用量和reliable queue，关闭付费、邮件、Creem、删除及YouTube。认证开关仅满足游客配置前提，不带Bearer；不可用供应商URL和不存在的本地会话reader占位不产生真实登录或认证连接。20个RFC5737独立IP/游客避免将游客一次额度与持续负载混淆，不放宽小时/日上限。

正式API上传、RQ、受限FFmpeg规范化、ONNX、分析/记谱、S3、带能力校验的下载票据与真实下载均进入本轮。不会调用重置人工评审的 run_human_regression；既有manifest/provenance/human-review/structure-review前后摘要须一致。下载可解析和运行成功不能代替听感、逐音参考或专业谱面评审。


## 实测结果

执行项目 venv 的 `/tmp/notavue-real-load-20261022.py`，一次运行退出0；随后 `/tmp/notavue-real-load-analyze-20261022.py` 重新核验结果与产物并生成统计。三份运行脚本、统计脚本及内嵌探针编译通过；本批没有生产代码变更，不重跑无关产品全量测试。

| 指标 | 本地观测 |
| --- | --- |
| 任务 | 20/20 succeeded，全部attempt1，10录音各2次 |
| 产物 | 100/100下载成功，字节数/SHA256一致；MIDI/时间线非空，MusicXML可解析 |
| 客户端总时长 | 142.054秒，含准入、轮询和逐项下载 |
| 发起POST至观察到RQ FINISHED | 最小10.9915秒，中位12.1711秒，样本nearest-rank P95为30.0905秒，最大30.0916秒 |
| 准入POST | 中位0.5439秒，最大1.0703秒，包含上传/裁剪/存储 |
| 任务查询 | 534次容器loopback，中位13.0375毫秒、样本P95 44.7毫秒、最大300.509毫秒 |
| health | 48次全部200，中位6.442毫秒、最大23.864毫秒 |

任务延迟从POST发起前计时，包含准入、排队、处理、0.5秒轮询休眠和查询开销，不是纯推理耗时。首两个任务约30.09秒，其余18个约10.99–13.56秒；未清空VM文件缓存，不称完整冷启动。20个任务重用了10段录音，样本P95仅用于本次固定工作负载描述，不能批准规范的生产P95；查询/health不包含TLS、公网、BFF、浏览器或多API负载。提交至观察终态区间最大重叠2，仅证明闭环区间重叠，不等同CPU同时忙碌或开放负载下的吞吐上限。

PostgreSQL得到20 GuestDay、20 GuestSubmission、20 JobDispatch和40 GuestLedger事件：每任务恰好1 reservation、1 consume，各游客reserved=0/consumed=1。20个RQ ID均FINISHED、worker_execution_count=1，客户端、数据库和下载产物的任务ID集合一致。Redis global active为0，小时安全计数合计20，没有重置限流或用量。全部成功使本轮没有失败release分支；静音3attempt及幂等/重复派发已单独记录在[上一批验收](2026-10-22-durable-batch-acceptance.md)，不冒称本轮验证了故障重试或崩溃恢复。

## 资源和收尾

| Worker | memory.peak | pids.peak | 生命周期CPU |
| --- | ---: | ---: | ---: |
| a，1 CPU/2 GiB | 728,166,400字节，694.434 MiB | 28 | 130.477 core-seconds |
| b，1 CPU/2 GiB | 708,919,296字节，676.078 MiB | 27 | 130.259 core-seconds |

资源来自内核cgroup；两者memory.events的max/oom/oom_kill均0，OOMKilled=false。CPU是容器累计值，包含启动、调度和采样，不是模型净CPU或云账单；两个各自峰值之和也不是同一时刻聚合峰值。本轮没有目标云价格或成本预算，不确认US$9.90/月经济可行性、不因142秒测试声称无长期内存增长。

任务后pipeline临时目录为空，两Worker正常stop退出0。finally精确清理本轮容器、私网及4卷（含Redis匿名卷），errors为空；主Agent事后只读检查本轮标签容器/网络/卷均空，并逐名inspect四卷不存在。没有全局prune、其它项目清理、全局Docker代理/context变更或外部邮件/付款操作。原四份manifest/provenance/人工评审文件完整摘要前后不变，输入原件未修改。

输入副本、来源/许可/摘要、143源码指纹、20任务状态历史、100实际产物、账本/RQ验证、cgroup/health、Worker/API日志及清理回执保存于 `.data/notavue-real-load-20261022`，目录0700、文件0600，不入Git；140份原始文件的摘要清单便于复核。

## 审查和保留边界

准备独立code-reviewer核对三脚本、实际Settings、十录音许可/摘要/时长、可信XFF/游客限额、对应RQ完成后补位和清理范围，未发现执行前可行动问题。统计审查指出原字段命名可能把POST起点误写为准入完成起点；分析脚本和本文已统一为发起提交至观察RQ完成，没有改变任何实测数值。

最终独立复核重新计算140份归档摘要，解析100个实际产物，核对20任务/账本ID、两Worker各10个预期RQ attempt、延迟/查询/health统计、143应用和四份既有评审摘要、资源/OOM、四卷回执及权限，未发现可行动P1/P2。审查者没有重演Docker，也未直接查询已销毁的PostgreSQL/Redis；账本和清理结论依据运行脚本、归档结果与日志交叉核对，不声称第二次独立实跑。

本批只是本机ARM64、20任务、约142秒的固定闭环负载。既有专业音乐评级/源码指纹门槛不因成功下载而通过，未实际听感/谱面专业复评；真实90秒/5分钟/10分钟、Free/Pro混合负载、长时间soak、故障风暴、云成本/生产权限、目标amd64与生产内核仍待验。FFmpeg漏洞、共享UID/后代进程隔离及yt-dlp独立调用等既有风险保留；不扩大副本、不勾完整38.5/BA-16、不批准上线。
