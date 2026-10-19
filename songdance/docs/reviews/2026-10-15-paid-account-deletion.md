# 2026-10-15 已退款付费账户删除验收

**已完成指定副本的真实浏览器申请、最近登录拒绝/重验、两批Worker删除及真实Google重新登录墓碑验证。** 本轮复用既有两笔Test付款/退款，不新增交易；限定验证所有已知订阅均已取消后的账户删除分支，不能替代active订阅自动停止续费、完整账本恢复或BA-13整体验收。环境收尾结果见文末。

## 隔离数据与身份

- 新建 `notavue_paid_deletion_20261015`，以第一笔真实交易验收库为模板复制数据库及6个存储文件，保留原业务user、身份、30秒消费、退款权益与真实转谱任务。使用独立存储/临时目录及Redis命名空间。
- 只读核对前两份付款账本及上一份已删除账户：三者的已验证issuer/subject完全一致，三个本地业务user ID不同。以该精确身份关系，将第二份账本唯一completed checkout意图导入新副本、映射到副本已有user；不是按付款邮箱合并，也不是用户可调用的生产迁移功能。
- 没有手工插入第二份BillingSubscription或PaidPeriod；两份订阅绑定均由原 `sync_checkout` 读取真实Creem checkout的request_id、customer、product、subscription后核实。原三库在准备前保存全表内容摘要，之后逐次只读比对保持一致。
- 新私密配置为 `.env.paid-deletion-test.local`（0600、默认所有功能开关false）。仅测试进程临时开启既定Test/Auth/用量/删除功能；不新建密钥、认证白名单、公开入口或外部订阅。Web只接收认证所需配置，不接收数据库或Creem凭据。

## 保留的失败与验收范围

首次尝试用原对账代码恢复两笔完整付款投影，聚合断言未通过。追踪确认：两份独立验收库中的付款周期在自然时间上重叠，将第二笔恢复进同一个用户时，原 `grant_paid_period` 正确抛出 `PaidPeriodConflict: paid period overlaps an existing grant`，即使原期已经revoked也拒绝。没有放宽规则、删除旧期、修改用量或手工插入重叠PaidPeriod。

第二笔checkout/订阅绑定已核验，但第二笔PaidPeriod未插入；对应对账事件由原 `process_pending` 保留为retry/PROVIDER_OR_BINDING_REVIEW、attempts=2。本副本仍只有原来一份revoked付费期、已用30秒。原第二份账本的revoked/已用0秒保持原样。本轮不把完整历史对账标为通过，也不以这个有历史投影冲突的副本证明正常多周期账本恢复。

另一次删除诊断在真实Creem GET查询时失败，事务已回滚。复查成功后再取得下述预检结果，保留失败审计，不将该次失败计为通过。

## 真实供应商删除预检

独立运行原 `verify_stopped_billing`，使用只允许GET的现有Creem客户端包装；任何POST会在网络调用前拒绝并记录。临时诊断申请和步骤均位于事务中，成功后回滚，没有留下持久删除申请或停用账户。

结果：顾客列表中的2份订阅均已绑定，逐一查询确认canceled，2份删除核验步骤达到verified；没有外部修改。准备快照为：user active/有邮箱、jobs=1、存储文件6、deletions=0、两份canceled订阅、一份revoked付费期/used30/reserved0，历史投影冲突事件仍保留。

## 真实浏览器与Worker执行

真实Google登录通过原PKCE流程返回独立副本 `/zh/account`，页面显示30秒历史消费和账单审查暂停。删除确认说明、勾选框及最终按钮均已实际查看；`snapshot-beforeconfirm.json`为active、有邮箱、1任务/6文件、无删除申请，财务摘要与ready完全相同。用户现场确认“确认，仅删除这个验收副本”后才提交。

1. 首次真实 `DELETE /me` 返回403，页面要求重新登录，持久删除申请仍0。准备/审查期间会话已超过10分钟，原最近登录保护生效；没有修改数据库时间、放宽门禁或把刷新JWT当重验。按页面“重新登录”退出并再次Google登录，再确认同一副本，DELETE返回202；持久申请pending/billing、attempts=0。记录的auth_confirmed_at距请求创建126.17秒。
2. 第一批原 `app.jobs.account_deletion --once`（仅替换Creem传输为GET包装）实际查询顾客列表及两份订阅，2份步骤verified后提交pending/cleanup、attempts=1，业务用户inactive。此时邮箱、1任务及6文件全部仍在，财务摘要与ready完全相同。
3. 第二批Worker完成清理：completed/cleanup、attempts=2，completed_at存在、邮箱为空、jobs=0、文件0；用户/identity各1，2份canceled订阅核验记录保留，原revoked付费期仍used30/reserved0，用量账本仍2行，历史投影retry事件仍attempts=2。
4. 第三次相同Worker运行handled=0，没有重复清理或外部查询。完整刷新真实账户页后显示“Notavue账户已停用”“账户删除已完成”，邮箱、套餐余额及任务入口均不再显示；原3库全表摘要始终相同。
5. 实际退出到登录页，再次通过同一Google/Supabase PKCE登录，页面仍停用/删除完成，已查看真实渲染截图。`snapshot-relogin.json`与completed快照除阶段标签外完全一致，未新增用户、额度、任务或财务变动。强制只读的本地身份诊断中，原/变更邮箱输入的业务访问均403，状态读取仍指向同一墓碑；这不是修改真实Google邮箱。

最终删除现场确认来自浏览器不可恢复删除规则，非项目技能额外要求。第一次按钮处于视区边缘，点击后没有产生请求；滚入视区后才发出上述403，未把无响应当作成功。所有实际API日志中该轮DELETE状态仅为403、202。

## 财务保留的逐字段复核

清理前后完整财务摘要不同，未直接标为“所有字段不变”。逐字段查询确认只有 `usage_periods.updated_at` 的一行变化：原 `_settle` 在检查既有consume终态前执行 `reserved_units=reserved_units` 以串行化，触发TimestampMixin的onupdate。没有新增release、退还消费或改变额度。

将这个明确的锁更新时间在内存中恢复为原库对应值后，所有8张财务表的内容摘要精确等于ready快照；其余字段、两条用量账本及30秒消费均未变。`completion-assertions.json`保留该断言，实际前后摘要在ready/completed快照中，未删除失败观察或忽略整张表。两份原账本和上一份已删除账户的全表摘要也仍精确一致。

截至完成断言，真实Creem审计共36次GET，其中准备阶段1次查询失败；实际删除Worker只有3次GET且全部成功，0次修改请求。历史投影冲突保持原retry状态，不把它伪造为processed或删除。

## 验收边界

原两份付款账本和原已删除账户均不作为删除目标。供应商始终仅GET，因此只能验证“已退款且已取消”分支，不能验证active订阅实际发送取消POST。真实双身份互访、完整正常多周期/失败付款/部分退款/争议及生产保留政策仍待验，BA-11/13不整体勾选。

临时入口为 `/tmp/notavue-paid-deletion-20261015.py`、`/tmp/notavue_paid_deletion_runtime.py`、`/tmp/notavue-run-paid-deletion.py`；脱敏准备、冲突、预检、快照及逐次请求审计保存在受忽略的 `.data/notavue-paid-deletion-20261015`。这些是本轮验收工具，未修改生产逻辑，尚未提交、推送或部署。

主要实际命令（仓库根目录；运行时凭据仅从本机私密配置读取）：

```sh
songdance/api/.venv/bin/python /tmp/notavue-resume-creem-test.py
songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py audit
songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py prepare
NOTAVUE_PAID_PHASE=preflight songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py preflight
NOTAVUE_PAID_PHASE=cancelled-preflight-retry songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py cancelled-preflight
songdance/api/.venv/bin/python /tmp/notavue-run-paid-deletion.py api
songdance/api/.venv/bin/python /tmp/notavue-run-paid-deletion.py web
NOTAVUE_PAID_PHASE=worker-billing songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py deletion
NOTAVUE_PAID_PHASE=worker-cleanup songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py deletion
NOTAVUE_PAID_PHASE=worker-idempotence songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-20261015.py deletion
songdance/api/.venv/bin/python /tmp/notavue-paid-deletion-final-check.py
```

完整对账`preflight`断言失败、第一次`cancelled-preflight`的供应商GET失败均如前文保留；重叠投影不标通过。限定取消预检复查、三批Worker（handled 1/1/0）和最终只读断言成功。浏览器操作使用原生Chrome工具，未通过脚本取得或伪造登录凭据。

## 独立审查与已执行检查

fresh `code-reviewer` 在准备与预检范围内未发现可行动问题。独立以强制只读连接确认三份原库全表摘要未变、目标副本无删除申请且财务摘要一致；确认6份存储文件内容一致但inode不同、无符号链接，配置0600且默认开关关闭，运行目录/队列隔离。离线测试5种修改请求均被GET包装在传输前拒绝；既有真实审计为33次GET，其中1次失败，没有修改请求。

审查者在API目录执行 `.venv/bin/pytest tests/test_account_deletion.py tests/test_account_deletion_client.py -q --tb=short -p no:cacheprovider --basetemp=/private/tmp/notavue-paid-preparation-review-pytest`，77项通过；`git diff --check`通过。主Agent已编译3个临时准备/运行脚本，核对新私密文件Git ignored/0600/默认flags false。生产代码无新增变更，未重复无关全量构建。

完成阶段另派fresh `code-reviewer`，在本次限定范围内未发现可行动的功能、安全或数据问题。审查者强制只读重核原3库全表摘要、目标completed/cleanup/attempts2、文件清理、身份/used30保留、唯一锁更新时间及8财务表摘要、36次GET/Worker3次成功和非GET拦截。另独立执行 `test_account_deletion.py test_account_deletion_client.py test_lifecycle_attempt_cleanup.py` 80项通过（9.01秒），`git diff --check`通过。77与80项范围重叠，不累加为新覆盖数。

审查者未亲自操作真实浏览器或重连Google/Supabase/Creem，没有验证active取消、双身份互访、完整账本恢复或最终停止服务；主Agent的浏览器事实不移作独立实测。

## 环境收尾

- 真实重新登录墓碑验证后，最后一轮会话已退出，实际页面回到 `/zh/login`。退出前浏览器审批服务曾返回403，随后原生连接中断；使用正常工具重连后完成退出，未绕过审批或通过脚本读取会话凭据。
- 已执行 `songdance/api/.venv/bin/python /tmp/notavue-stop-paid-deletion.py`：按本轮PID与命令核对后关闭Web自有4进程、API1进程；Redis按PID/run_id核对后关闭，原隔离PostgreSQL按postmaster.pid核对后fast stop。3002/8002及本任务PG/Redis端口连接检查均关闭，资源清单`stopped=true`，四份业务数据库及审计保留。
- 新私密配置保持0600、Git ignored、所有默认功能开关false；未新开Hook/Tunnel、邮件额度或供应商回调。必要的Google/Supabase身份、业务墓碑、账单、用量和冲突事件保留。
- 在Web目录执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen` 退出0，生成引用恢复 `.next/types/routes.d.ts`。本轮没有生产代码变更，未重新跑无关Web构建。
- 最终 `git diff --check`通过；4份相关文档24个本地链接有效、无尾随空白。22份待交付文本未命中四份实际私密配置中的key/secret/DSN/bridge值，四配置均0600且默认开关false。提权只读`lsof`确认3002/8002/8025/8027/58776/58777均无监听，停止清单与端口连接断言一致。
- 改动尚未提交、推送或部署。下一项仍需针对正常完整账本、active停费和真实双用户分别取得有效证据；本轮指定分支完成不代表完整BA或发布批准。
