# 2026-10-21 支付失败、原 checkout 恢复与部分退款记录

本轮三次官方失败卡/零授额、原单关页重开及唯一成功付款/重复对账已通过；用户停止新订阅续费，累计退款USD11.60/实付USD11.78，剩余USD0.18因Test余额不足待退。全部服务已关闭。下文保留准备阶段事实，最新状态以真实执行与收尾为准。

准备阶段：新建隔离库 `notavue_payment_failure_20261021`，Google 目标在该测试库没有旧付款；保护邮箱账户保留原全退账本。原9库和来源文件摘要不变，配置开关关闭，全部服务停止，无供应商调用、付款、发信或公网入口。

## 本轮验收合同

关闭收银台、卡拒付和 checkout 过期是不同事实。官方 GET checkout 枚举为 pending、processing、completed、expired，没有支付卡失败对应的 checkout failed 枚举；本地 failed 意图用于商品核验失败或明确创建拒绝，不能用它冒充真实拒付。

本轮先观察拒付、余额不足、CVC 错误后仍无付费期/付费用量/订阅绑定；关闭收银台再回原 Pricing，继续购买应复用同一原 checkout，不新建第二单。若供应商确认 expired，则原意图可持久过期，本地测试证明新幂等键才能新建；但本轮供应商创建预算拟仅1个，现场遇过期必须停止，不自动追加预算。随后同一 checkout 成功付款，原权威对账只授1800秒一次，重复对账不改原 grant。

第三方收银台及商户操作由用户完成，应用不存卡号/CVC。拟 Google 登录、付款邮箱 support@notavue.io；允许供应商复用昨天同 Google 的 support 客户，按本轮新 checkout/request_id/subscription/transaction 逐项核验，不宣称客户一定新建。两个旧保护客户仍排除，旧订阅/交易不操作。结束由用户取消本轮新订阅、累计全额模拟退款，Agent只读核对；无自动取消、Portal、邮件或删除账户。

## 官方文档核验

2026-10-21 使用 agent-reach 网页读取路线：Jina 域名初次沙箱解析失败，获准公开读取后超时；按现有7897代理直接读取官方 Markdown 成功，没有携带私密凭据。

- [Test Mode](https://docs.creem.io/getting-started/test-mode)：成功卡 `4111 1111 1111 1111`；拒付 `4507 9900 0000 0028`；余额不足 `4507 9900 0000 0010`；CVC错误 `4507 9900 0000 0044`。有效期用未来日期，CVV/账单信息按 Test 文档；不会处理真实资金。
- [GET checkout](https://docs.creem.io/api-reference/endpoint/get-checkout)：核对状态枚举、request_id、product、units 和 provider id。

公开原文保存本轮私密 tools 以便续接；文档抓取只证明公开合同，不证明本商户已经触发真实拒付。

## 代码和隔离准备

新增 `api/tests/test_checkout_payment_recovery.py` 共6个参数化用例：pending/processing 未付状态只复用原链接且无授额，随后原通知/对账成功授一次；三次同事件及 active 不重授；仅供应商确认 expired 后新key才可新建，旧记录保留；pending/failed/voided 非付款交易即使 checkout completed 也拒绝授额。后3种交易状态是离线不可信输入反例，不宣称都是 Creem 实际输出枚举。本批未改生产逻辑，不改变产品规范。

新库从 template0 建库并正式 Alembic 迁移；只导入精确 User/AuthIdentity，两份身份与来源逐字段一致。Google 目标在新测试lane空财务图是隔离夹具设计，原所有库（含昨天已删除墓碑）不重置、不清历史，也不作为生产迁移。保护邮箱的7张财务表原字段导入，全退/revoked/canceled 图保留。

两身份各显式复制1任务/6storage文件及1个合成pipeline临时文件，重写ID/文件键，清reservation/guest引用、dispatch=false；仅用于隔离保护，不是本轮新上传、模型或真实消费验收。来源9库和源storage在准备前后及独立只读复核摘要相同；摘要不覆盖数据库物理文件/schema/序列。配置0600、外层0700，独立storage/tmp/Redis/queue；10个API功能开关与Web Auth均false。

受限 provider 要求精确本轮 scope 才允许任何供应商调用，当前文件不存在。拟最大1 checkout POST，合同990分USD/1800秒/90秒、units整数1、服务端固定回跳；先持久一次门闩，创建结果未知不重复 POST。GET仅本商品、目标本地意图对应 checkout、该 completed checkout 所绑定 subscription/latest transaction；付款总额须整数990..1200，拒绝越界/bool/float。拒绝取消、Portal、商户交易/客户列表和其余写操作，API拒绝所有DELETE及OTP-start/attempt/Portal。真实站点沿用原 Pricing/Account/Return 页面，不另造绕过生产按钮的结账入口。

私密 unpaid 检查脚本只GET并严格核同 provider id/request_id/product/units；pending/processing/expired 均不授额、不建订阅；completed则记录 unexpected 并停止后续卡尝试。浏览器拒付错误文字必须由用户提供，不能从 checkout 仍 pending 推断具体拒付原因。paid 检查仅原服务GET核验与投影，重复保留同一 grant/usage id 和引用。

## 已执行验证与失败记录

在 `songdance/api` 实跑 `.venv/bin/python -m pytest -q tests/test_checkout_payment_recovery.py tests/test_creem_failures.py tests/test_creem_billing.py`：44 passed；`.venv/bin/ruff check tests/test_checkout_payment_recovery.py` 通过。保留 Starlette/httpx、pkg_resources 两项已有依赖弃用警告。

根目录实跑 `PYTHONPATH=songdance/api:/tmp songdance/api/.venv/bin/python -m pytest -q /tmp/test_notavue_payment_failure_guard_20261021.py`：21 passed；只读 unpaid/paid 执行脚本离线10项通过，覆盖未付三状态、不匹配/意外completed拒绝、相同原grant重放。全部使用临时SQLite/存储，不访问现库或供应商。

准备脚本 `/tmp/notavue-prepare-payment-failure-20261021.py` 和单独只读复核 `/tmp/notavue-verify-payment-failure-preparation-20261021.py` 由同一venv实际执行通过。仅恢复本机隔离PG，二者均finally停PG；新外部授权前另补存两身份14表及全部storage/tmp精确基线，重复准备复核通过；Web/API/Redis未启动，无默认配置导入或外部写。原9库、来源storage、保护7财务表、目标空财务、两身份/文件数量及scope缺失均核实。

fresh 独立审查发现三项P2并修正：来源清单误含尚未创建的本轮配置，改为既有active-deletion第9来源；正常stop曾在leader消失时跳过后代，现runtime记录自建PGID，stop验证组内命令并对全组TERM/必要KILL、确认无非zombie成员及五端口关闭后才标stopped。准备前已修，不存在真实运行半成品。独立6恢复用例与21 guard再次通过，孤儿后代清理修复通过隔离mock；第三项为unpaid两次GET间恰好过期会混用报告与投影状态，现仅取一次权威快照、用严格同id的深复制快照供原服务核验，新增过期边界反例通过；独立最新10项复跑通过。真实运行进程树仍须下一轮启动/停机核实。

## 下一实际阶段

尚未取得本轮真实支付授权，未创建 checkout 或付款；scope不存在，供应商调用0。拟申请1 checkout、3次官方拒付测试、同单最多1次成功付款（商品USD9.90、含税不超USD12）、结束用户只处理该新订阅的取消与累计全额退款。只用Google登录，不开邮件Hook/Tunnel/Portal，不删账户。需要第三方操作时给用户当前一步；原测试付款额度不沿用。

真实拒付/关页恢复/成功/退款、原供应商事件投递、完整BA-07–10/14均未签收。普通/离线检查和准备记录不代替现场结果，完整商业化、音乐质量和生产部署门槛保留。

最终独立文件证据复核无遗留可行动问题：每身份14表基线、目标7财务表为空，实际12storage+2tmp摘要与保存基线完全一致，来源摘要9项、scope/调用审计缺失；三文件计数与范围一致。主Agent最后实测五端口关闭、PG停机、10API+Web开关关闭和私密权限，脚本/公开原文已归档。审查者未重新连接现库或供应商，也未重跑实际服务；真实拒付与付款仍待新授权后现场完成。

## 限定真实执行（更新上述准备态）

用户明确授权本轮1个checkout、三张官方失败卡各最多1次、同一checkout关页重开后最多1笔成功Test付款（含税不超USD12），结束由用户仅取消该新订阅并累计全退。第三方由用户操作，scope按精确预算私密落盘；Google登录、不发OTP/不启Hook/Tunnel/不生成Portal/不删账户/不自动取消。

原Pricing按钮实际创建唯一pending checkout，Test总额用户核为USD11.78、付款邮箱support@。拒付、余额不足、CVC错误三张官方卡各由用户提交一次，三次页面原文均为“付款被拒绝。请尝试其他银行卡或付款方式。”，没有显示具体余额不足或CVC原因，不能宣称UI区分三类失败。每次随后受限GET同一原checkout均pending；原服务检查目标PaidPeriod、付费用量、订阅绑定均0，没有第二次创建。

用户关闭收银台，从同一Google会话的原账户/价格页重开；再次GET核原checkout仍pending、supplier POST总数1、未授额，总额仍USD11.78。随后用户用官方成功卡完成本轮唯一成功付款；权威GET核同一checkout completed、订阅active、交易paid/1178分USD，精确关联request_id/product/customer/subscription/transaction，原服务只授1800秒/used0/reserved0。再次GET对账后target五财务表逐字段不变，PaidPeriod仅1份；用户刷新真实账户页确认Pro/1800秒。此现场重复为原GET对账，不冒充真实webhook重放；重复通知仅有本地回归证据。供货商允许复用同owner的历史support客户，本轮不宣称新customer。

## 部分退款差额，未全额完成

用户已停止本轮新订阅续费，申请累计全退时只成功退USD11.60；剩余USD0.18提示“余额不足。请等待传入的付款后再申请退款”。Agent只读精确本轮交易/订阅确认partialRefund、amount_paid1178/refunded_amount1160、订阅canceled；不以用户操作意图当全退成功，不新建付款补余额，不重试退款。

原内部对账队列使用同一交易金融指纹持久review/PARTIAL_REFUND_REVIEW，保留active PaidPeriod及1800/0/0，不按比例扣额度、不生成全退取消补偿。相同指纹再次入队为false、处理0，review/attempts保留。无新的供应商写；最终审计POST仅原checkout创建1次，卡支付和商户取消/退款均由用户操作。完整退款、全退后的权益撤销及退款重复恢复仍未签收，差额记录保留待供应商允许退款后再核验。

部分退款脚本首次离线检查及独立审查发现报告保存误调用不存在的save方法，会在本地提交后缺少结果文件；真实执行前改为record_consistent。新增1项临时SQLite用例修前复现失败、修后通过，覆盖1160/1178/review/active、重复0和首次/重复报告落盘；独立同1项及4项相关生产回归通过，无遗留可行动问题。实际受限脚本 `/tmp/notavue-payment-failure-partial-refund-20261021.py` 由项目venv执行成功，仅GET本轮tx/sub；未调用裸账单worker、取消或全商户扫描。

## 完整性和收尾

实际只读完整性脚本核原9库摘要/源storage不变，保护owner14表全字段不变，全部12storage+2tmp文件摘要与授权前基线一致；目标users/auth_identities、任务及4子表保持，删除申请0。供应商POST仅1checkout、其他写0。目标财务变化仅本轮checkout/绑定/1800权益及部分退款review记录；原历史账本不清除。

用户确认退出Notavue应用。stop首次遇Next实际构建子进程不匹配命令守卫，已停止API后安全中止，未标全停。只读核该成员位于本轮记录PGID且命令为本轮专用 `.next/notavue-payment-failure-20261021/dev/build/` 下node worker；仅补精确build目录前缀允许，再执行原组清理通过。最终API/Web/Redis自建进程组全部为空，PG停止，3002/8002/8024/58781/58776五端口实际关闭，配置0600/外层0700、10API和Web Auth开关全false。没有开过邮件/隧道、删除账户或改系统网络，全部数据与失败记录保留。真实启动和正常组清理此次已取得现场证据，启动失败/孤儿边界仍对应之前离线mock。

本轮指定支付失败不授额、原单关页恢复、成功及重复对账只授一次已通过。部分退款人工对账已核，剩余18分导致全退收尾仍待处理；不将整个付款/退款闭环或BA-07–10/14勾为完成。本批不改生产代码，不重做上一模块44项/31项已通过检查；新增部分退款1项及独立4项针对新增脚本路径，未重跑音乐/模型或生产部署。

最终独立只读审查未发现可行动问题：三文档与失败3次/重开pending、POST1、成功1期/重复五表同、1160/1178部分退款和18分差额一致，实际12storage+2tmp摘要与基线相同、关联源码归档一致。stop精确build前缀正反匹配检查通过，配置权限/开关符合记录。原9库及最终进程/端口/PG状态依据主Agent执行证据核对，审查者未重启服务或连接供应商。


## 用户决定停止补退（2026-10-21）

用户再次尝试原交易剩余USD0.18仍收到余额不足，随后明确选择“停止补退，保留部分退款记录并继续其他验收”。因此该差额作为未退事实保留，本轮不再自动/人工引导重试退款，不调用退款API、不充值、不新增付款补余额，也不等待支持回复作为其他验收的前置条件。原权威状态仍以最近已核实的partialRefund/1160对1178、canceled、review/active1800为准；本次没有新供应商读取，不能声称状态再次刷新或全退完成。

全退恢复脚本曾在临时SQLite和独立审查下验证部分退款拒绝、模拟全退后revoked/verified及repeat0，仅为未执行准备；因缺全退事实未恢复PG或执行真实流程。上次自动审批服务403使记录保存和端口复核命令未执行，不将那次检查标为通过；本轮同样不启动任何原测试服务。下一项改为独立本地续费/到期边界验收，不混用或修改本轮旧账本。
