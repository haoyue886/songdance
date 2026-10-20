# 2026-10-20 供应商客户复用冲突：退款收尾与修复

本轮双付费客户真实补验**未通过**：Creem Test把邮箱新付款返回为Google原付款已使用的同一customer，无法获得两份不同客户绑定。原数据库唯一约束拒绝串绑且未授额；随后已对本轮唯一新交易 **USD9.90（990分）全额模拟退款，并确认新订阅canceled**。原五库和Google七张财务表摘要未变。

现场发现并修复另一个产品缺陷：客户冲突原先触发IntegrityError回滚，付款用户一直停在payment_confirming。修复将目标账户和checkout持久置为待审，旧绑定保留，不自动合并、授额、重购或清理未解决义务。真实隔离库与账户页复验通过；双客户前提仍不成立，BA-11/13未整体签收。

## 授权与真实范围

用户授权本轮最多1个checkout、1笔Notavue Pro Test模拟付款（商品990分、含税上限USD12，现场最终确认USD9.90及条款），Google/邮箱各最多1次Portal，原最多1次OTP及随后明确补充的最多1次OTP；临时入口仅两条验签邮件回调，限额保持2/h，Creem webhook保持关闭。验收后全额Test退款并核实停止续费。本轮未开启Live、未操作真实资金或删除供应商身份。

先前预检及原库复制已提交 `29f78da`，记录见 [双客户准备](2026-10-19-two-paid-customer-preparation.md)。目标为新库 `notavue_two_paid_20261019`，原五库只读核对；flags在0600私密配置中仍全false，仅运行时授权启用。测试脚本与证据保存在Git忽略的 `.data/notavue-two-paid-20261019`，不提交凭据/客户链接/数据库。

## 邮件连接与真实登录

首个授权OTP在代理后的TLS握手阶段超时，状态unknown；次数门闩拦截第二回调，用户确认未收到，不手工重试该未知请求。无凭据GET诊断三轮冷连接两次在TLS超过2秒，成功后的连接复用339ms。

测试专用预热传输在启用Hook前无凭据GET建连，复用原ResendClient的2秒请求/3秒总界限、证书校验和零重试。独立审查发现断线时仍可能冷建连的P2，已用HTTPX trace在连接操作started阶段拒绝新的TCP/Unix/TLS操作修正；锁定httpcore1.0.9。真实连接池+离线socket的正常复用、Connection:close、空闲断线等 **7项通过，独立复审P2关闭**。失败结果不复位持久发送预算；没有修改生产邮件代码或系统代理。

跨夜Quick Tunnel被Cloudflare注销，进程存活不代表入口可用；旧入口期间请求未到签名listener、补充send marker未创建，不等同第二次供应商发信。重建同范围入口，更新同一Hook并重验无签名401/业务404；刷新过期的无凭据连接后，唯一补充发送Hook **200，487.82ms**、delivery accepted。用户在Chrome无痕完成hello@登录；普通Chrome Google会话另行核对。随后Hook原UI确认DISABLED，mail与Tunnel均退出，无剩余发送额度。

## 新交易、冲突与收尾

原BFF+API验收页确认email业务owner，仅调用一次受限POST /checkouts，provider返回pending。收银台Test Mode、Notavue Pro Test、当前总额USD9.90/月，用户现场确认后提交；没有额外税费。付款返回本站后，回跳参数不授额，原sync_checkout用provider GET查询completed及active新订阅。

该provider customer已绑定Google业务user，新邮箱account.customer_id写入触发 `uq_billing_customer`。事务回滚，邮箱仍无customer/subscription/PaidPeriod；没有把旧客户转移给邮箱或绕过唯一约束。独立审查用全新离线SQLite也复现这条生产失败路径，确认旧绑定完整且新用户永远payment_confirming。

为安全清理，私密脚本串联验证：唯一邮箱本地checkout→权威completed/request_id/product→新subscription→latest transaction/customer/990USD，且新subscription不在Google历史绑定集合。商户Test页对该新交易全额990分退款并选择取消其活跃订阅；后台GET确认transaction refunded、amount_paid=refunded_amount=990、subscription canceled。未执行额外API取消POST，不伪造本地绑定。原Google所有历史订阅均未取消或变更。

两份Portal授权均未使用；双客户矩阵未开始，不能因发生了一笔付款宣称两客户验收通过。checkout及新付款额度已用完，不自动创建第二笔来绕过冲突。

## 产品修复

`billing_events.py` 在已核实checkout合同后检查customer是否已归其他user；并发首次绑定用savepoint和唯一索引仲裁，冲突不会使整个外层事件事务失效。只将目标account blocked、新open checkout uncertain/CUSTOMER_BINDING_CONFLICT、支付链接清空；旧customer、订阅和额度保持。历史terminal checkout保持终态并记录同一冲突标记，允许与另一新pending共存。已核实冲突不因重复事件、远端退款/过期或晚到创建响应而清除；checkout事件明确review。

`billing.py` 对冲突checkout返回review_required、隐藏旧支付链接，晚到POST创建响应不能改回pending；原摘要使用blocked显示待审，重复购买仍409。`account_deletion_billing.py` 明确拒绝任意terminal/open checkout的未解决客户冲突，使义务不因历史终态跳过删除核验；删除已进入cleanup或completed时发现迟到冲突，会重开为billing/review、保留DELETION_CUSTOMER_CONFLICT并清除完成时间，后续Worker停止清理。已经完成的文件或邮箱删除不会恢复，财务义务仍保留供人工复核。无需迁移或更改既定AUTH/BILL合同；不自动把相同email当归属凭据。

聚焦回归先复现3失败，再验证direct/event/完整reconcile、重复与退款后状态、无效provider合同不可阻断账户、晚到创建响应、PG同customer首次并发绑定等场景。fresh审查先后发现历史completed改uncertain与已有pending冲突，以及cleanup/completed删除单未重开两个P2；均已修复并补回归，最终fresh复审未发现可行动问题。独立审查相关 **82 passed、1 skipped**，跳过的是其本轮未再次启用的一次性PG并发项；执行者相关 **165项通过**，另含PG的聚焦 **12项通过**。主Agent最终复跑命令及结果：

- 在api目录运行 `.venv/bin/python -m pytest -q tests/test_billing_customer_conflict.py tests/test_billing_recovery.py tests/test_billing_worker.py tests/test_billing_ui_contract.py tests/test_account_deletion.py tests/test_account_deletion_client.py`：**171 passed、1 skipped**；skip为显式opt-in的PG测试。
- `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/python -m pytest -q tests/test_billing_customer_conflict.py`：**12 passed**，自建并清理一次性PostgreSQL，包含并发唯一客户绑定。
- 四个范围文件的Ruff与 `git diff --check` 通过。此前前端既有组件 **21项通过**；本批未改Web代码，不冒称全量Web/E2E或完整商业验收通过。存在既有Starlette/httpx与pkg_resources弃用警告。

## 修复后的真实复验

使用原受限BoundedProvider执行一次sync_checkout，仅供应商GET和本轮隔离库写入，不调用裸Worker CLI。目标持久为blocked=true、checkout uncertain/CUSTOMER_BINDING_CONFLICT、checkout_url为空、customer_id为空，且无subscription绑定或PaidPeriod；billing_state为review_required、portal_available=false。重启已核对归属的本轮8002 API后，原Chrome无痕邮箱账户页刷新显示“账单状态需要人工审查，新任务和新购买已暂停”，购买和Portal入口均不存在。Google账户刷新仍为原Pro 1770秒/已用30秒及既有待审状态，管理账单入口保留；未调用Portal。

最终只读完整性脚本确认原五数据库摘要、Google七张财务表逐字段摘要不变；邮箱只新增本轮冲突待审投影，未串绑或授额；退款与停止续费证据保留。失败前的final-financial-integrity.json未覆盖，修复后另存final-financial-integrity-postfix.json及conflict-review-projection.json、页面截图，均在私密忽略目录。首次沙箱连接本机PG被拒，正常提权后对账及完整性核对通过，没有将连接失败当业务失败或更换数据。

## 最终收尾

Chrome普通Google与无痕邮箱均从原账户页点击退出，分别确认返回登录页，无痕窗口随后关闭。仅停止经PID及完整命令核对的本轮API/Web/Redis及隔离PG集群，临时public验收页已移除。3002、8002、8024、58781、58776五端口实测关闭，私密两份配置均0600且落盘feature flags禁用；数据与证据保留。Send Email Hook先前原UI已确认DISABLED，mail/Tunnel均停止，Creem webhook全程关闭。调用审计确认checkout POST恰1次、Portal POST为0；不再发邮件、付款或生成Portal。

## 仍需完成的验收

真实双客户需要两个不同Creem客户，目前没有这项证据；下一轮先核对测试客户的邮箱去重行为，再明确新客户输入及新的交易授权，不能移动原Google绑定或默许再付一笔。两个同时active付费客户、真实同邮箱身份注册策略、active删除停费、云端多副本、法律/容量/音乐质量与LA门槛继续保留。

用户已选择亲自完成后续第三方软件/网页操作。当前下一步仅在Creem Test Mode只读核对：从2026-10-20本轮USD9.90已退款交易打开关联客户，核对客户当前邮箱，并确认同一客户记录是否同时列出10月14日/此前Google验收付款与本轮付款。只需反馈邮箱是否为hello@notavue.io、两轮交易是否在同一客户名下，无需提供凭据、完整客户标识或带签名链接。当前客户邮箱不能单独证明历史收银台实际填写的邮箱；客户复用原因仍待核实。本步不新建checkout、付款、Portal或改动客户/订阅。
