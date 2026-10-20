# 2026-10-20 干净已退款账户的删除与真实重登录验收

**已完成指定副本的真实OTP登录、删除申请、两阶段Worker清理及真实重新登录墓碑验证。** 原UI删除先403、重新认证后202；Worker处理1/1/0，先核实停止续费并停用，再清理目标1个复制任务、6个存储文件、1个临时文件及邮箱。重登录仍指向同一completed墓碑，没有新用户、身份、用量周期或任务。目标身份/财务记录、Google保护账户及原七库未变。最终全部测试服务关闭、五端口实测关闭，用户确认邮件Hook Disabled并退出无痕会话。

这是已全额退款且订阅已取消的指定分支，不能签收active订阅实际取消、真实Google/Supabase身份删除或完整BA-13；复制任务无用量预占，本轮不声称真实consume/release或音乐质量通过。

## 隔离范围与授权

新库 `notavue_refunded_deletion_20261020` 从[本轮已全额退款账本](2026-10-20-distinct-payment-email-preparation.md)克隆。目标为hello@邮箱业务身份，其独立付款客户只有一份真实revoked付费期与一份canceled订阅，原交易累计退款1178分等于实付额；没有此前付费删除副本的重叠历史投影冲突。Google身份是副本内保护对象，七份来源PG库不是删除目标，供应商身份和Creem记录均不删除。

目标原本无任务。为覆盖清理，只在新副本复制Google旧任务及6个存储文件，重写任务/asset/result/artifact ID、owner及storage键，清空用量/游客预占、禁止派发、单独设24h期限；这是明确复制夹具，不代表目标新上传或模型结果，也不制造用量。另建1个显式合成pipeline临时文件；保护任务及6文件独立保留，目标/保护任务前8位不同，避免临时目录前缀混淆。

storage/tmp/Redis/queue/mail均独立。两份私密配置0600、外层目录0700，实际加载全部10个Settings功能开关和Web auth落盘false，受限runtime仅在内存开启既定验收功能，analysis保持关闭。源码、配置、数据库、身份/客户引用及证据位于Git忽略的 `.data/notavue-refunded-deletion-20261020`，不提交密钥、身份ID或签名链接。

用户先授权两次登录邮件/临时两条签名HTTPS入口，最终确认只删上述新副本目标和1任务/6存储/1临时文件；原身份墓碑、用量及账单保留。后续最近登录窗口和验证码失败分别获额外1次发送授权，总上限4，initial/reauth/reauth_retry/relogin各一次，全部有独立持久门闩。原最终删除范围不变，不重复索取同目标授权，不新建付款或Portal。

## 准备、预检与运行边界

准备脚本实际克隆新库并复制文件，前后七来源PG库全public表数据摘要相同，来源storage/mail摘要相同；数据摘要不代表数据库文件/schema/序列逐字节一致。临时启动固定本机PG后finally停机，未清理源库或文件。

真实预检仅受限4次GET确认目标交易refunded、amount_paid=refunded_amount=1178 USD分、新订阅canceled。事务中模拟AccountDeletion，调用原verify_stopped_billing得到1个verified步骤，再finally rollback；持久申请/步骤0，目标active/邮箱及全部任务文件保留，PaidPeriod revoked/UsagePeriod1800/0/0。保存目标/保护账户、全部账单事件和源库基线后停PG，未把模拟步骤当成真实删除。

供应商provider只允许目标精确checkout/subscription/transaction/product与该客户订阅分页GET，所有写及他人客户查询在网络前拒绝。API沿用原JWT验签、只读Supabase会话查询和业务身份映射，再对DELETE限制目标owner；保护owner DELETE403，checkout/Portal POST403。最近登录时间仍由原Verifier读取，不改认证时间、不放宽10分钟门禁。专用Worker显式注入BoundedProvider，未运行会创建普通CreemClient的裸CLI。

## 保留的失败、邮件预算与限额

初次OTP accepted/Hook200后，用户打开原账户删除确认页并明确最终目标。用户首次点击反馈已提交，但实际日志DELETE403、申请0；主Agent提交断言及随后的Worker存在性断言均在修改前失败，没有停用/清理。用户确认页面要求重新登录，原最近登录保护生效，未将概括反馈当202证据。

用户额外批准reauth一次。无凭据连接预热先ConnectTimeout，mail启动退出且没有发信；确认进程已退出、预算未用后恢复。reauth邮件有一次accepted/Hook200，但用户验证失败，后续又发起新发送请求，被ACCEPTANCE_TRANSPORT_NOT_READY拒绝，未调用Resend；本地认证请求随后429。无法从固定安全错误证明验证码具体失败原因，不归咎用户或供应商，不把它记为成功登录。立即停止mail/Tunnel，用户确认Hook Disabled，只读诊断Redis计数和冷却，不读验证码/会话凭据，也不重置限流。

用户再批准reauth_retry一次，总上限4。原2封/小时未调整，initial/reauth邮件接受时间为北京时间18:43:41/19:17:43；实际19:41:57检查仍未到允许窗口，等待至19:43:51后才恢复同一副本。等待期间服务全停，Redis AOF、授权和旧门闩保留；恢复前确认旧PID已退出，不以回复文本代替时间条件。新reauth_retry邮件accepted/attempts1，时间19:52:51，用户在同一无痕页面使用最新邮件登录并立即提交删除。未在未知发送后自动重发。

第三方Hook配置、登录、页面状态及退出由用户操作和明确反馈，Agent核对本机日志/账本，未冒称亲自目视第三方页面。每次入口启用前严格TLS核对两无签名回调401、业务/me404；发送前刷新无凭据连接，成功后立即停mail/Tunnel并请用户禁用Hook。限额保持2/h由用户确认，不通过提高限额推进。

## 原接口受理与两阶段清理

原API/PG核对最终唯一目标DELETE202，auth_confirmed_at距申请创建46.157868秒；先前403保留。申请pending/billing、attempts0，目标直到第一批Worker前仍active。用户不可恢复删除确认保存在私密目标授权文件，Worker还校验固定副本/owner/阶段及存储目录。

1. billing批次仅GET重新枚举目标客户、核对绑定订阅canceled；1个停费步骤verified后提交pending/cleanup、attempts1、用户inactive，邮箱/任务/6文件/1tmp仍在。七源库、来源mail、保护账户14模型表及文件、目标8张身份财务表与全部billing事件摘要均与before相同。
2. cleanup批次completed/cleanup、attempts2、completed_at存在；邮箱清空，目标复制任务及source/artifact/result/quality四从表行清除，6存储文件和1临时文件清除。身份映射、revoked付费期、用量和账单精确保留；Google保护账户14表、6文件字节、原七库、全部账单事件不变。
3. repeat批次handled0、attempts仍2，没有重复删除或供应商请求。真实供应商审计共6次成功GET（预检4+Worker2），无写调用，不新增Creem取消或身份删除。

用户刷新原账户页确认“账户已停用／账户删除已完成”，不再显示邮箱、套餐余额或任务入口，退出到登录页并确认Hook Disabled。Agent停全部服务、五端口关闭，保留completed快照和最后relogin未用额度。

## 真实重新登录墓碑

最后relogin仍按2/h窗口执行。最早20:17:53，用户于20:48明确继续后Agent检查实际时间已满足，才恢复同一completed副本；未创建新库或再次删除。新邮件入口就绪、用户确认Hook启用和登录页就绪后刷新连接，最后邮件accepted/attempts1、Hook200，四phase门闩全部消耗，剩余发送授权0。

用户以hello@最新OTP在原无痕页重新登录，明确确认仍停用/删除完成、没有邮箱/套餐余额/任务入口。原API日志新一轮/me200、billing/me403，与Supabase新登录流程及停用状态相符。只读 `relogin` 验证在有用户真实新登录反馈后执行，副本完整快照与completed完全一致：仍同墓碑，User2/Identity2，目标仅原1用量周期、无目标任务/子表，目标8身份财务表及所有billing事件不变，保护14表/6文件和七来源库/来源mail不变。没有按stage参数独自冒充真实登录证据；未修改真实身份供应商账户或邮箱。

用户最后确认Hook Disabled、退出登录回到登录页并关闭无痕窗口。mail/Tunnel立即停止，其余API/Web/Redis/PG按PID/命令核对后停止；3002/8002/8024/58781/58776五端口实测关闭，私密配置仍0600、10开关False，全部墓碑/账本/失败及限流证据保留。没有自动化、后续发信或供应商修改。

## 验证、独立审查与证据边界

主Agent在API目录运行 `.venv/bin/python -m pytest -q tests/test_account_deletion.py tests/test_account_deletion_client.py --tb=short`：77 passed。临时guard18项通过：目标GET白名单5、写/他人读拒绝8、身份guard4、真实FastAPI+SQLite/FakeVerifier原路由1。脚本编译及文档链接/diff检查通过，生产代码未改，不重跑无关全量Web/API/模型验收。两条既有Starlette/httpx和pkg_resources弃用警告保留。

fresh准备/runtime/preflight/Worker/恢复脚本分别独立复审无可行动问题。独立guard18项、隔离FastAPI12断言通过；纯离线模拟验证PG启动超时/resources写失败finally清理、canceled预检回滚、active取消在网络前拒绝；Worker无授权/目标错/阶段错提前拒绝，离线1/1/0及保护数据完整。恢复脚本未到窗口/预算已用/旧PID存活均零dispatch；每phase仅一次、重启不复位、unknown消耗预算，保留Redis数据。未把这些离线检查当真实OTP/付款或供应商取消测试。

实际删除结果独立只读复核确认原403→202、1/1/0、保护14表/6文件、目标8身份财务表及账单事件不变，实际目标storage/tmp已无。审查者未连接现PG或供应商、未执行真实Worker；七源库/端口和用户页面反馈保留各自证据来源。目标UsageLedger原本0行且复制任务无reservation，只验证空流水保留；真实消费/释放由[另一本地两期账本测试](2026-10-20-paid-history-deletion-local.md)覆盖，不移作本轮真实验收。

私密核心证据为delete-submitted.json、worker-billing/cleanup/repeat.json、full-copy-before-deletion.json、completed-copy-snapshot.json、verified-billing/cleanup/relogin.json、initial/reauth-retry/relogin-email-result.json、reauth失败/限额与额外授权记录、user-relogin-and-exit-confirmation.json、final-shutdown-verification.json及原API/provider日志。旧准备、403/验证码失败、等待停服报告不覆盖删除；最终状态以本节及最终收尾报告为准。

当前只签收一份干净全退账本、已取消订阅的真实删除和同身份真实OTP重登墓碑。active停费取消、真实完整多周期供应商账本、云端多实例、法律保留政策和完整BA-13仍待验。本轮未新增付款/Portal，未删除Google/Supabase身份或Creem记录，原七库及保护客户保留。

最终三文档及真实relogin/收尾证据经独立只读复核无可行动问题：用户页面/退出记录、最后accepted一次/四门闩用完、原API新auth及/me200/billing403、completed重登快照一致、provider6GET/无写和DELETE403→202一致。配置权限/关闭、resources stopped及PG pid不存在已核对，文档链接与diff检查通过。未重跑测试/触网/访问现PG；用户第三方页面、原七库/端口证据来源保持明确，不扩大审查范围。
