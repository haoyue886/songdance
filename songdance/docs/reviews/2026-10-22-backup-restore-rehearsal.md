# 2026-10-22 PostgreSQL／私有对象逻辑备份恢复演练

基线 `06e04dd`。本批只在随机本地internal网络及一次性资源验证恢复过程，没有修改产品代码、生产配置或依赖，不部署、不推送，不连接原商业测试账本或真实供应商。第二轮成功标识 `eea9197c43`，API/Worker固定为已验证ARM64镜像 `sha256:6f986ec08f678b3829e9cb2dc706521a2df48d363e8ccb58e787cc743efa2630`，现仓库应用代码与该镜像既有143文件证据一致。

## 演练范围

正式API以reliable queue开启、其余认证/用量/商业/邮件/YouTube/分析开关关闭的隔离配置上传2秒合成A4，任务持久化后停API且不启动Worker。随后只在新测试库补充合成的活跃账户和用量预占、已删除账户/身份墓碑、历史Free/已撤销付费期及消费记录、已处理账单事件、游客消费和提交墓碑。这里是直接构建历史夹具，不是实际登录、付款、退款或账户删除流程复测。

停止写入后，用PostgreSQL16容器内 `pg_dump --format=custom --no-owner --no-acl` 备份应用数据库；另按key导出一个源WAV对象的字节、Content-Type、Metadata及SHA256。两份本机归档计算摘要并在恢复前再次校验。源API、数据库、Redis停止；新建独立空PostgreSQL数据库、临时应用卷、全新空Redis和新私有桶，在同一临时MinIO服务中恢复对象。新桶是逻辑副本，不是跨云或整台S3服务器丢失后的灾难恢复。

数据库使用 `pg_restore --no-owner --no-acl --exit-on-error --single-transaction` 恢复到经确认无public表的新库，未覆盖源库。对象逐字节、类型和元数据对比；不依赖ETag代表内容摘要。API恢复启动前，比对所有public表的行集合、字段序列化哈希和行数。

## 实际结果

- 执行 `songdance/api/.venv/bin/python /tmp/notavue-backup-restore-20261022.py` 第二轮退出0。源库为迁移014，共28张表、26行合成记录；恢复后各表完整字段和行数逐项相同，包含空表。没有验证全局角色/ACL、数据库扩展、生产备份调度或PITR；本演练有意不导入原owner/ACL。
- 一个源对象恢复到新桶后，字节SHA256、Content-Type和Metadata相同。该测试不覆盖已有完整任务产物、大对象、多版本、生命周期、加密或真实云桶权限；源/目标桶共用本轮MinIO服务。
- 恢复Redis的DBSIZE与队列均为0。原Dispatcher运行一次后队列1条；测试夹具将同一个outbox的next_attempt_at设为当前时间，再跑Dispatcher，队列仍为同一条RQ ID。这个时间调整仅为触发重复发布验证，不作为生产恢复时批量改deadline的建议。
- 原生产Worker入口 `python -m app.worker` 在2 CPU/2 GiB/128进程限制下处理恢复任务，数据库succeeded、RQ明确FINISHED、execution_count=1、attempt_count=1，五类产物均成功。再显式调用原Worker任务入口两次，仍只有一份reservation和一份consume，active用量从reserved=1/consumed=0变为0/1。验证没有额外结算或产物数量增加，不外推为所有故障窗口都只执行一次。
- 任务恢复后，users、身份、删除、paid_periods、账单账户/事件、游客账本和提交墓碑的完整字段哈希不变；已删除账户的历史usage_periods两行及usage_ledger四行也完整字段不变。删除夹具仍inactive且邮箱为空，付费期仍revoked、历史消费仍保留；没有真实重新登录或向供应商重新核账。
- 从开始pg_restore到恢复任务验证/Worker关闭约34.449秒，排除前置创建目标实例、取回备份、人工操作、DNS、云权限等耗时。这是本机小样本区间，**不是生产RTO/RPO承诺**。
- Worker无OOM，pipeline临时目录为空且SIGTERM退出0；finally精确删除本轮容器、私网和命名卷，并用 `docker rm -f -v` 移除Redis默认匿名卷。收集到的7个卷均逐名inspect确认不存在，清理errors为空；事后本轮标签容器/网络/卷查询为空。未运行全局prune或处理其它项目卷。

## 失败与审查

首轮 `a57a837552` 在目标PostgreSQL初始化临时服务切换时，pg_isready已响应但下一次psql连接失败，退出1，尚未执行pg_restore；脚本清理其全部7卷和容器/网络，失败日志与归档保留在私有attempt-1目录。就绪检查改为PID1是最终postgres且pg_isready成功，随后用全新资源完成第二轮，不把第一次失败标为通过。

准备独立审查发现并修复4项P2：历史用量只比计数而未比全部字段、Redis匿名卷未登记、仅DB成功而未强制RQ FINISHED、清理前采集失败会阻断实际清理。独立离线检查覆盖历史记录改写/删除检测、RQ状态四分支及清理采集超时/写文件失败等反例；两份脚本编译通过。最终审查重新计算28表/26行和历史哈希、两份备份摘要及对象字节，核对空Redis、重复派发、RQ FINISHED/执行1/五产物/一次消费、两轮卷清单、143应用指纹和文档链接，未发现本批遗留P1/P2。审查未重演Docker或查询daemon，资源清理结论依据已审脚本、回执及主Agent实际查询。

脚本、两轮数据库/对象归档、摘要、28表指纹、对象证明、队列/RQ/账本结果与精确清理清单在 `.data/notavue-backup-restore-20261022`，0700目录、0600文件，不入Git。这里只是合成测试归档，未提供生产加密备份、异地副本、密钥托管或定时任务。没有因本轮只有文档变更重跑无关产品全量测试。

## 生产仍需核验

正式恢复必须先关闭公开写入口及所有Worker/Dispatcher/账单/删除/邮件定时任务，协调数据库与对象的一致快照，再恢复到隔离新目标并检查。不能把Redis空库视作恢复了运行限流计数；恢复后应先核对运行成本预算和持久预占，再恢复新请求。数据库中的过期时间和删除墓碑不能重置；备份时间点之后发生的删除、付款、退款等须另行核对并重放其权威事实，避免把旧快照中的账户/权益重新激活。

真实云PostgreSQL/S3、全局角色和最小权限、备份保留/加密、演练频率、PITR及正式RTO/RPO、完整账单跨周期/外部对账、认证会话、目标amd64/生产内核和专业音乐质量仍未验收。FFmpeg漏洞及进程隔离边界继续保留，本次逻辑恢复通过不批准上线。
