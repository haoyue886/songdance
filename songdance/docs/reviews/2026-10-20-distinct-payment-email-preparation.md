# 2026-10-20 不同付款客户的真实隔离验收与退款受阻

**指定双客户账单/Portal矩阵通过，真实全额退款闭环未完成。** 原Google付款客户与本轮邮箱账户的新付款客户ID不同；两身份各6条隔离请求、各1次本人Portal共14个编号结果符合预期，Portal前后财务快照未变。本轮Test实付USD11.78，首次退款因余额不足失败；用户先取消订阅，随后自行重试退款。最新权威GET为partialRefund、已退USD9.90、尚有USD1.88差额，新订阅仍canceled。本地已进入PARTIAL_REFUND_REVIEW，PaidPeriod保留active及1800/used0/reserved0，没有伪造全额退款或按比例扣量。后续处理见文末。

所有本轮服务已停止，临时页面已移除，五端口实测关闭。原六份来源PG库、来源mail和Google七张财务表摘要未变。BA-11/13不整体勾选，两个同时active客户、完整付费删除和本轮真实退款/repeat继续待验。

## 授权、身份与隔离

用户核对旧Creem客户邮箱为hello@notavue.io，两轮旧交易均归该客户；[首次付款记录](2026-10-14-creem-test-integration.md)也明确Google应用身份付款时收银台使用hello@。因此上一轮不同应用身份却相同付款邮箱，未满足独立客户前提；失败、全额退款及客户冲突修复保留在[上一轮记录](2026-10-20-provider-customer-conflict.md)。不能由当前邮箱单独推断Creem内部去重规则。

本轮用户选择原Google账号的Gmail作为付款邮箱，应用仍以hello@邮箱身份登录，亲自操作第三方网页。用户明确授权最多1个checkout/1笔Notavue Pro Test月付（商品USD9.90、含税不超过USD12）、两个客户各最多1次Portal、必要时hello@最多1次OTP及两条临时签名邮件回调（2/h），完成后全额模拟退款并停止续费。第三方提交由用户执行，本地检查/受限GET由Agent完成，没有Live付款、充值或真实身份删除。

新库 `notavue_two_paid_distinct_20261020` 从10/19原账单隔离库克隆，未清除或重置旧冲突库。旧冲突库和其他五份来源库纳入全public表数据摘要保护；摘要不代表数据库文件、schema、序列逐字节一致。新副本初始只有Google原退款客户绑定及30秒已用历史，邮箱无客户/checkout；两身份按精确issuer+subject映射，没有伪造客户/付款/额度。storage/mail复制到独立目录，tmp、队列、Redis命名空间独立。

新两份私密配置为0600、外层目录0700，实际加载全部10个功能开关为False；仅受限runtime在内存中开启本轮已授权功能，账户删除/音乐分析保持关闭。凭据、客户引用、数据库、源码和证据位于Git忽略的 `.data/notavue-two-paid-distinct-20261020`；不提交身份ID、客户ID、配置或签名链接。

## 本地准备与脚本验证

准备脚本正常执行：新库初始摘要与模板匹配，前后六来源PG库摘要一致，来源mail SHA不变；独立审查确认storage六文件哈希相同、mail副本与来源SQLite全表逻辑摘要相同。仅临时启动本机原隔离PG完成克隆，然后停机。

准备审查发现并修复启动超时后清理遗漏及默认True的analysis开关未显式关闭：启动和首次resources写入现均位于try/finally内，枚举Settings全部_enabled写false。纯离线故障测试 `/tmp/notavue-test-distinct-prepare-cleanup-20261020.py` 两项通过，覆盖启动超时但已有pid、资源文件写失败后stop且原异常传播。初次测试被沙箱socket预检阻断，探针离线替身后才验证清理分支；最终独立复审无可行动问题。

受限runtime/start/stop及本地验收页审查通过，provider门闩主Agent/独立各9项通过：checkout一次、每持久客户Portal一次、越界拒绝及未知结果不释放预算。实际Next/子进程停止由主Agent最终执行并核对端口，审查者当时的进程树读取因沙箱EPERM未覆盖实际停服。

本轮临时对账脚本执行前审查发现必需交易ID漏参和引用落盘后失败无法恢复：已传transaction_id及expected_latest_transaction，已有引用只读精确比较、不覆盖。隔离SQLite/离线provider下先2失败1通过，修复后3通过；随后新增“已取消但未退款保留付费权益”分支，最终主Agent及独立各4通过，覆盖付款→退款→repeat、失败恢复、冲突持久review、取消不等于退款。两条既有依赖弃用警告保留。生产代码未改，不重复宣称上一批业务回归为本轮运行。

临时测试曾在API tests目录执行，已移出仓库并与runtime、准备/停机/对账脚本保存到私密tools。JS语法 `node --check`、脚本编译、文档相对链接及 `git diff --check` 通过；未运行全量Web/API/E2E，不扩大为完整商业或音乐质量验收。

## 邮件与真实会话

用户先在普通Chrome登录原Google账号，并打开Supabase Auth Hooks。本轮临时mail/Tunnel启动后，严格TLS校验下无签名两回调401、业务/me404。首次urllib探测因证书链失败，改用既有代理和certifi校验通过，未关闭证书校验；Supabase地址在交付用户前按实际路由修正为/webhooks/supabase/email。

用户保留原签名密钥、保存启用Hook后，主Agent核对预算未使用和精确PID/命令，仅刷新mail连接；原次数门闩未删除。用户无痕hello@发送一次，Hook200、最新delivery accepted/attempts1，用户确认已登录。随后mail/Tunnel按归属停止，用户确认Hook Disabled；剩余邮件授权0。邮件核对脚本初次相对as_uri失败，resolve后通过，未改变或重发邮件。授权限制2/h保持，未在本轮独立重查第三方限额页面。

第三方配置、登录成功、Portal内容及最终退出均取用户明确反馈；Agent核对本机日志和数据，没有冒称亲自操作/目视第三方页面。本轮Google/邮箱会话分别位于普通和无痕Chrome。

## 付款、矩阵与Portal结果

新checkout前保存Google七财务表全字段摘要。用户确认临时页identity=email，仅创建一次checkout；用原Gmail在Test Mode完成付款并回复已付款。GET-only对账脚本串联核对completed checkout的request_id/product/new subscription/customer/transaction、990分USD合同、实付1178分在1200分上限内，新客户ID与Google旧绑定不同。原sync_checkout+sync_transaction投影PaidPeriod=active、新订阅active、额度1800/0/0，无供应商变更请求。证据为new-trade-refs.json、reconcile-paid.json、integrity-paid.json。

两份Portal用户核对邮箱匹配：Google应用身份对应旧hello@付款客户，邮箱应用身份对应新Gmail付款客户。API的两portal-create编号均200，provider审计每owner成功POST恰1次。

用户首次概括“两边通过”时，日志没有matrix编号请求，主Agent断言失败并保留事实，没有把identify的passed=true或Portal成功当矩阵通过。用户随后只补两窗口“检查本人的账单隔离”，明确确认kind=matrix、complete:true/ passed:true。主Agent验证器通过14个唯一编号结果且各出现一次：两身份own/query GET200、各四个注入他人user_id/customer_id的Portal/checkout body POST422，另两次本人Portal200。

页面先核对/me身份、本人summary.owner_id、伪造query响应与本人summary深度相等，再执行后续body拒绝并确认private/no-store与portal_available。HTTP日志证明状态/顺序，响应内容断言结合用户matrix结果反馈，Portal内容结合用户实际页面核对。独立审查只读核对14编号/页面规则/provider owner，无可行动问题，未访问当前PG或第三方，不扩大为独立真实浏览器验收。

Portal后及补矩阵后两次只读integrity确认：六来源库/来源mail/Google七财务表不变，邮箱七财务表与Portal前快照相同，checkout POST1、Portal POST2、供应商取消POST0。相关证据为matrix-api-verification.json、user-matrix-portal-confirmation.json、integrity-portal.json、integrity-portal-after-matrix.json。

## 退款余额不足、停止续费与待办

用户在Creem Test对本轮Gmail客户USD11.78新交易申请全额退款，页面提示“余额不足。请等待传入的付款后再申请退款。”受限GET随即确认transaction paid、amount_paid1178、refunded_amount=null、新订阅active，不能记录退款成功。未新增付款、充值、切换Live或重试退款，也未猜测等待期、模拟余额机制或最终可退款时间。

用户单独取消该新订阅并确认停止续费，后续GET确认status=canceled、future_renewal_stopped=true，交易仍paid、未退款。已独立复审的stopped分支仅用供应商GET同步本轮新库：PaidPeriod active、额度1800/0/0保持、subscription canceled，未运行process_cancellations或真实refund/repeat，无供应商退款/取消POST。取消不撤销已付款周期符合既定合同；没有为了通过验收手改revoked或清除交易。

停服前integrity-stopped.json再次确认六来源库、来源mail及Google七财务表不变。本轮身份、已付记录和独立客户绑定保留；真实全额退款、退款后revoked/准入和repeat验收仍受阻，不能用4项离线回归替代。私密refund-blocker.json及两份refund-blocked-status时间戳报告保留错误和前后状态。本地已准备未发送的 `creem-support-draft.zh.md`，由用户自行提交Creem官方支持，询问Test余额/测试结算规则或环境恢复方法；不发送凭据、完整账本或.env。没有创建等待/监控自动化，也不承诺退款何时可用。

## 最终收尾与后续

用户确认两Notavue会话均退出并返回登录页、无痕窗口关闭，管理员会话保留。按PID及命令核对停止本轮API/Web/Redis和隔离PG，移除临时public验收页；mail/Tunnel此前已停止。3002/8002/8024/58781/58776五端口实测关闭，两份私密配置0600且全部10开关关闭，数据/次数门闩/证据保留。用户确认Supabase邮件Hook Disabled，Creem webhook全程保持关闭。最终检查存在一条Pydantic实例model_fields弃用警告，断言通过，没有更改生产依赖。

当前交付仅签收两个不同真实客户下的指定summary/query/body/Portal矩阵及新订阅停费。完整BA-11/13、两同时active客户、真实付费删除、云端多实例等仍待验。本轮退款由供应商Test余额阻断，后续取得支持答复后再决定是否恢复只读核验或重新申请退款；不自动新建checkout/邮件/Portal，不修改原客户或旧账本。最终证据为final-shutdown-verification.json、shutdown.json及integrity-stopped.json。

最终三份文档及私密证据独立复审无可行动问题：逐条核对14编号各一次、两个退款受阻GET状态、stopped权益保留、provider审计20成功GET及仅3次成功写（1 checkout、2 Portal）、私密配置全部开关关闭/0600、PG pid及临时页不存在，来源mail SHA不变。审查者未启动服务、触网或访问PG，六来源库/Google摘要和五端口沿用主Agent实际执行证据，用户退出/第三方Hook禁用保留为用户反馈；真实退款/repeat无证据文件且未冒称通过。

## 续接：用户重试后为部分退款，待核对差额

用户先反馈“已有答复”，随后说明重新尝试后退款成功，尚未提供官方支持答复正文。Agent没有发送支持消息或再次请求退款。立即使用原不可变交易/客户/订阅引用受限GET核对：status=partialRefund、amount_paid=1178、refunded_amount=990、currency=USD，新订阅仍canceled。明确告知用户USD1.88差额并请其只读查看页面退款金额、税额或处理中记录，不推断差额已退/必定稍后退，也不把本轮partialRefund当作全额refunded。尚未执行全额退款/repeat脚本。

按既定BILL-03部分退款人工对账规则，仅临时启动固定隔离PG，以GET-only provider再次核验相同事实，再通过原内部_queue_transaction及process_pending写入持久reconciliation.transaction：review/PARTIAL_REFUND_REVIEW，PaidPeriod active、额度1800/0/0、新订阅canceled，无退款取消意图。相同财务指纹重复入队false、处理0，review及attempts不复位；邮箱七财务表在重复前后完全一致。

执行前独立审查发现临时脚本提交入队后失败无法恢复的P2，已按原财务指纹定位精确本轮事件，允许其既有pending/retry恢复或review补证，拒绝其他待处理事件；既有证据只读精确比较不覆盖。临时离线回归共7项通过（原付款/退款/重放/取消4项，加含税部分退款/外来客户拒绝/处理器GET失败后到期恢复3项），独立7项通过及复审无可行动问题。只对测试中的retry时间显式置为已到期，真实投影未提前重置退避或审查状态。生产代码未改；wrapper启动/停机失败路径本轮为静态审查，正常路径已实际执行。

主Agent实际partial投影两次、邮箱七表重放比对及六来源PG库/来源mail/Google七表完整性核验通过；仅新副本增加部分退款审查事件，没有修改原库。wrapper在finally停止PG，Web/API/Redis/mail/Tunnel均未启动，五端口再次实测关闭，两配置0600且全部10开关False、临时页仍不存在，供应商写调用仍仅原1 checkout+2 Portal。此前paid未退的阻断记录与final-shutdown均保留，新增partial-refund-projection.json、partial-repeat-verification.json、integrity-partial-refund.json、partial-final-shutdown-verification.json；部分退款重放不冒称完整退款repeat通过。
