# 2026-10-20 干净已退款账本的真实删除验收准备

目标为新的独立副本 `notavue_refunded_deletion_20261020`，来自[本轮已全额退款账本](2026-10-20-distinct-payment-email-preparation.md)。目标是邮箱应用身份hello@的业务账户，新客户只有一份真实已退款PaidPeriod和一份canceled订阅，没有旧验收副本的重叠历史投影冲突。Google身份在副本内为保护对象。**当前仅准备，不签收删除结果；尚未创建持久删除申请，也未执行删除Worker。**

本轮拟覆盖已退款、已取消账户的删除及真实邮箱重新登录墓碑，不覆盖active订阅实际取消、真实Google/Supabase身份删除或完整BA-13。第三方网页由用户操作，最终不可恢复删除须针对本副本明确确认；新增OTP/临时签名邮件入口需另取限定授权，不复用已耗尽邮件预算。没有新付款/Portal计划。

## 已完成本地准备

准备脚本 `/tmp/notavue-prepare-refunded-deletion-20261020.py` 已成功：临时启动固定本机PG、克隆新库、复制独立storage/mail/tmp/Redis队列命名，finally停PG。原七份来源PG库（含失败冲突库、已完成双客户全退库）全public表数据摘要前后相同，原storage/mail未变。原库不是删除目标，摘要不代表数据库文件/schema/序列逐字节不变。

目标原本无任务，为验证文件清理，只在副本给它复制Google的1个真实旧任务及6文件，重写job/asset/result/artifact等ID、owner和storage键，清空用量/游客预占、禁止派发、期限单独设24h；不改变目标已用秒数或历史权益，不冒称新上传/模型结果。这1任务及6文件是显式复制夹具，另有1个合成pipeline临时文件。原Google任务及6文件仍独立存在，目标与保护任务前8位不同，避免临时目录前缀混淆。

两私密配置0600、外层目录0700；全部10个Settings功能开关及Web auth落盘false。仅后续受限runtime按授权在内存启用auth/usage/billing/deletion，analysis仍关闭。mail数据库只有本地审计副本，不代表获准发信；准备期外部调用0，新付款/Portal/邮件次数0。源码、配置、账本、身份/客户引用和证据均保存在Git忽略的本轮data目录，不提交密钥或标识。

准备独立审查未发现可行动问题；审查者纯离线mock验证PG启动超时但已产生pid及resources写失败均走finally停机，write_env经原load_settings核对10开关/Web auth false、0600。实际复制/七源库摘要是主Agent执行证据，审查者未启动PG或访问供应商。

## 运行边界与检查

`/tmp/notavue_refunded_deletion_runtime_20261020.py` 限供应商GET，并限定目标客户的精确checkout/subscription/transaction/product和该客户订阅分页。任何POST（包括取消/Portal/checkout）在网络前拒绝；原verify_stopped_billing若发现仍active无法修改供应商，只会阻止删除继续。

临时本机API额外缩小DELETE /me的可操作账户：原account_status_user的JWT/会话/业务映射照常执行，然后只有manifest的目标owner可删，保护Google请求403。最近登录验证仍由原路由/Verifier执行，不修改认证时间或绕过权限。POST checkout/Portal入口固定403；没有启用生产身份删除。

主Agent临时离线测试18项通过：5条目标GET白名单、8条写/他人查询拒绝、4条身份guard分支、1条真实FastAPI+SQLite/FakeVerifier路由检查（保护owner删除403、目标无最近登录REAUTH_REQUIRED、最近登录后仅目标202、他人/me可读、checkout/Portal403）。这不是当前副本的真实DELETE，没有连接原库或真实身份。两条既有依赖弃用警告保留。

准备脚本及runtime/preflight语法检查通过，生产代码未改。临时检查暂存API tests目录运行，交付前移至私密tools；最终范围不包含这些一次性测试文件。

## 待完成

停费预检脚本只临时恢复PG，用受限GET核对原交易全额1178分退款和canceled订阅；在事务中模拟删除、调用原verify_stopped_billing核验，再rollback并确认申请/步骤持久数0、目标active/邮箱/账本/文件保留；保存目标/保护账户及事件摘要，再复核七来源库并停机。该脚本已独立复核并实际执行，结果见下节；不能以准备报告代替真实GET。

预检通过后再准备原账户页确认流程。目标使用hello@邮箱登录，至少需首次和删除后重新登录两次验证码，若超过最近登录窗口还需另行处理；不得自动扩大发送额度或请求未知重发。删除目标固定为本新副本中hello@业务账户及复制夹具，源七库、Google保护账户、Supabase/Google身份、Creem账单均不删除。

## 真实预检结果与当前停点

`/tmp/notavue-refunded-deletion-preflight-20261020.py` 已实际成功。受限4次GET确认原目标transaction为refunded、amount_paid=refunded_amount=1178 USD分，新subscription canceled；原verify_stopped_billing生成1个verified步骤。模拟AccountDeletion、步骤及可能的订阅状态刷新均在finally rollback，之后持久申请/步骤0、目标active及hello@邮箱保留、PaidPeriod revoked/UsagePeriod1800/0/0。原七来源PG库全public表摘要与准备基线相同、来源mail SHA相同，目标和保护账户10张模型表逐字段摘要、全部billing事件摘要已保存，不在聊天输出标识。

准备与运行层分别fresh审查，无可行动问题。独立18项guard及隔离FastAPI 12条断言通过（供应商调用0）；预检审查另离线mock验证启动超时/resources写失败finally停止、canceled验证后申请/步骤/投影回滚、active时取消在网络前被拒绝且回滚。审查者未连接真实供应商或现PG，实际4 GET和七源库摘要为主Agent执行证据。后续Worker必须显式用本轮BoundedProvider驱动，不能直接运行会创建普通CreemClient的裸account_deletion CLI。

主Agent `.venv/bin/python -m pytest -q tests/test_account_deletion.py tests/test_account_deletion_client.py --tb=short`：77 passed，两条既有依赖弃用警告。临时18项guard通过，脚本编译、文档相对链接及diff检查通过。未修改生产逻辑，不跑无关全量Web/模型检查。

finally已停止PG，未启动Web/API/Redis/mail/Tunnel；五端口3002/8002/8024/58781/58776实测关闭，两份配置经原各自load_settings核对全部10功能开关False/0600。证据prepared-stopped-verification.json记4次成功供应商GET、0写、0删除申请；源码及临时测试移到私密tools，仓库不留临时public页或测试。目标复制任务、6文件和1临时文件保留，尚未实际删除。

下一步需用户限定授权：为了原邮箱身份首次登录和删除后真实重新登录墓碑，最多各1封hello@验证码（共2次发送尝试），复用签名密钥并临时恢复原两条签名邮件HTTPS回调/Hook，保持2/h；无checkout/付款/Portal或身份供应商删除。第三方UI由用户操作，最终账户删除还需在准备好的目标确认页另行明确确认。若发送未知或门禁超时，不默许额外邮件；若总耗时超过每小时限额，按原限额等待，不临时提额。当前授权未取得，所有服务停在关闭状态。

后续专用Worker驱动也已独立离线复核：缺授权文件、目标不符、阶段不符均提前拒绝，隔离SQLite中billing→cleanup→repeat处理1/1/0、保护账户任务/文件不变且供应商只GET。该结果不表示已对真实副本创建授权或执行删除；正式驱动仍等待最终目标确认。
