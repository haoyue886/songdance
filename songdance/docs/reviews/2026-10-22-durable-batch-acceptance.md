# 2026-10-22 游客账本与可靠派发连续小批次验收

基线 `ec3e522`。本批没有修改产品代码、依赖或生产配置，只运行本地合成输入的隔离验收并记录结果；不部署、不推送、不连接原商业数据库或供应商。成功运行标识 `5a6f25dc7f`，API/Worker 固定为 ARM64 镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`。重新计算当前143个应用 Python 文件摘要，与该镜像既有绑定证据逐项相同。

## 范围与执行

随机 internal 网络中运行一次性 PostgreSQL16、Redis7.4、固定源码 MinIO、API 和两个正式 `python -m app.worker`。每 Worker 限1 CPU、2 GiB、128进程，无宿主端口或数据挂载。开启 reliable queue、游客/用量及分析；关闭付费、Creem、邮件、删除和 YouTube。认证开关仅满足游客配置前提：无 Bearer 请求，Supabase URL 为不可用占位，会话 DSN 使用临时 PG 上不存在的 offline_reader 角色，没有调用认证或建立真实身份。

实际命令为项目 venv 执行 `/tmp/notavue-durable-batch-20261022.py`，后者在 API 容器执行 client/verify 两脚本，通过真实 HTTP、PostgreSQL、Redis/RQ、S3 和 ONNX 模型验收。三份脚本 `py_compile` 通过；第二轮主入口退出0。所有脚本和原始结果归档到 `.data/notavue-durable-batch-20261022`，目录0700、文件0600，不入Git。

依次运行三轮，每轮两个不同游客各上传2秒合成 A4。每轮第一个游客以同一 Idempotency-Key 并发提交两次，要求同任务、同能力 token；成功后重放仍同任务，以新 key 创建则拒绝。另一个游客上传2秒静音，真实模型失败后以幂等 retry key 重试到第三次尝试，第4次尝试必须拒绝。这里不是登录 Free/Pro 账户矩阵、真实曲目质量或持续压测。

首轮两个任务持久化入队后暂不启动 Worker。测试夹具仅将已有 outbox 的 next_attempt_at 设为当前时间，两个正式 Dispatcher 并发重复发布，再核对队列并启动 Worker；这个时间修改只为触发重复发布，不是生产运维建议。

## 实际结果

- 三轮共6个成功任务，各仅 attempt1、5类产物成功；同 key 并发/成功重放均保持原任务，每轮新 key 均为 `429 GUEST_TRIAL_USED`。首对任务的并发 Dispatcher 前后队列始终为相同的2条 RQ ID。
- 静音任务三次均为业务 `failed / NO_NOTES_DETECTED`，无产物。每次 retry key 重放返回同一任务及同一 attempt，没有额外递增；第4次尝试 `409`。失败游客最终 reserved=0、used=0、remaining=1。
- PostgreSQL 共7任务、7 GuestDay、9 GuestSubmission、9 JobDispatch、18 GuestLedger事件。6个成功任务各1 reservation/1 consume；静音任务3 reservation/3 release。每个 reservation 恰好一个终结事件，没有重复扣量或释放。
- 9个 RQ attempt 均明确 FINISHED，worker_execution_count 各为1。业务失败是函数正常记录的终态，因此 RQ FINISHED 不代表业务成功。没有覆盖所有崩溃/网络丢失/Redis重启窗口，也不宣称任意故障下 exactly-once 执行。
- Redis global active 最终0，小时安全计数合计12：6次成功任务准入、3次已用游客的新 key 拒绝、静音3次尝试。幂等重放没有额外计数；业务失败释放预占，但不退回安全计数。没有清空或放宽限流指标。
- 两 Worker 的 cgroup memory.peak 分别667,619,328和658,681,856字节，约637/628 MiB；pids.peak 为29/27，memory.events 的 oom/oom_kill 均0，容器 OOMKilled=false。任务后 pipeline 临时目录为空，两 Worker 正常 stop 退出0。
- client 按顺序等待每对任务，记录的 wait_seconds 是从各自开始轮询到 RQ 完成的时间，第二个通常已完成；不能把接近0的第二项当作推理延迟，也不能据此计算生产P95。这里只提供有界小批次的账本/去重和资源观测，不估算云成本。
- 两轮 finally 均无清理错误。每轮4卷（含 Redis 默认匿名卷）逐名 inspect 确认不存在；主 Agent 事后只读核对两轮标签容器/网络/卷均空。未运行全局 prune，也未清理其它项目资源。

## 失败、审查与限制

首轮 `21bf64c13b` 在 API 启动前的配置校验停止，尚无 client/任务结果：私有脚本把临时业务库 postgres 管理员 DSN 用作认证会话配置，现有 auth_config 拒绝。修为不建立角色、不连接的 offline_reader 占位 DSN 后第二轮通过；首轮失败与清理回执保留在 attempt-1，不把它计为成功批次。没有为本轮增加会话读权限或绕过产品校验。

准备独立 code-reviewer 发现客户端仅等业务终态、未等 Worker 释放并发名额的时序 P2。离线真实 API 复现了该窗口的 ACTIVE_JOB_LIMIT；私有 client 改为同时等对应 attempt 的 RQ FINISHED，再开始下一次准入。独立 mock 及第二轮实跑通过，未修改生产执行顺序。审查另以实际 Settings 校验占位配置，并在禁止 socket 连接时验证无 Bearer 路径不连接认证服务。

收尾核对发现 docker cp 后的 client-result.json 继承0644，父目录始终0700，内容不含能力token；最终已统一文件0600并逐项stat断言。原执行版脚本保留，另存复制后立即chmod的修正版及两版摘要，修正版编译通过但未重跑Docker。文档链接、证据计数和 git diff --check 通过。

最终独立复核重新计算30份证据摘要、143应用摘要，并交叉核对7任务/9attempt/18账本/12安全计数、Worker日志中的9个独立RQ ID、资源记录、两轮8卷清单/清理及事后空标签结果；未发现剩余可行动问题。审查者未重演Docker，也未直接查询已销毁的数据库/Redis；运行与清理结论依据实际验证脚本、归档日志/结果和主Agent事后只读核对，不宣称额外独立实跑。

没有因本批只有文档变更重跑无关产品全量测试。现有 FFmpeg 漏洞、同 UID/后代与聚合资源隔离边界、yt-dlp 独立调用、目标 amd64/生产内核和云备份权限仍未解决。真实曲目持续并发、完整 Free/Pro/游客混合负载、故障成本、生产P95及专业音乐复评仍待验；本批不勾选完整38.5/BA-16、不批准扩副本或上线。
