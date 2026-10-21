# 2026-10-21 支付失败与原 checkout 恢复验收准备

本地准备完成，真实拒付尚未执行。新建隔离库 `notavue_payment_failure_20261021`，Google 目标在该测试库没有旧付款；保护邮箱账户保留原全退账本。原9库和来源文件摘要不变，配置开关关闭，全部服务停止，无供应商调用、付款、发信或公网入口。

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
