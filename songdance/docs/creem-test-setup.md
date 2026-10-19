# Creem Test 后端接入

2026-10-14：指定 Test 项目已完成真实 Google 登录、Test 卡付款与 1,800 秒到账、约 30 秒转谱/三格式导出、Portal 取消续费及全额模拟退款/权益撤销。临时 webhook 和本机服务已关闭，默认开关仍 false；完整 BA 与生产验收未完成。实际证据、修复和未验项见 [真实联调记录](reviews/2026-10-14-creem-test-integration.md)。

2026-10-15：保持 webhook 禁用，已用第二笔授权模拟交易补验漏付款/退款通知时的真实对账恢复、单页两笔商户历史、active 订阅退款后由应用自动取消一次并查询确认、重复对账不重授额/不重取消，以及退款后UI/退出。两笔均已全额模拟退款，账本保留、服务关闭。多页/跨周期/部分退款/争议等剩余条款见 [补充验收记录](reviews/2026-10-15-creem-reconciliation.md)。

## 配置和运行

先完成 auth-setup.md 的身份配置，在隔离数据库运行 `alembic upgrade head`（本轮 head 为 014）。参考 `../infra/env.creem.example`，密钥仅放到未提交环境文件。配置认证、用量和付费用量，再启用 CREEM_ENABLED。Test 商品须为 USD 990 cents、every-month、无 trial/usage_prices；1,800 秒和 90 秒单次为当前 Test 快照，不代表 5/10 分钟已验收。

本轮商品名为 Notavue Pro Test，资源 ID 沿用。受限 Test key 仅需 checkouts read/write、products read、customers read/write、subscriptions read/write、transactions read，关闭 Full access；退款由授权商户控制台操作，应用不需要 refunds write。真实创建 API 拒绝 `127.0.0.1` 的 success URL，本机应用已按授权统一使用 `http://localhost:3002`。Supabase 测试 Site URL 同步为该地址，allowlist 保留 localhost/127.0.0.1 两条精确 `/api/auth/callback`；测试/生产域名分别维护。

API 提供 `POST /billing/checkout`（空 JSON、已登录 Bearer、本站 Origin、8–128 位 Idempotency-Key）和 `POST /billing/portal`（空 JSON、同样身份/Origin）。服务端决定 product、customer、金额和回跳地址。公共 `GET /billing/config` 驱动页面数字；私有 `GET /billing/me` 提供状态及 owner_id/checkout_key，终态匹配才清除对应浏览器幂等键。前端 /pricing、/account、/billing/return、/refund、/contact 已接入。success URL 使用本站 /billing/return，已有 /account 配置也兼容；回跳不授权。`SONGDANCE_SUPPORT_EMAIL` 只有配置并核实可用后才显示邮箱。

在 Creem Test 控制台配置精确 webhook URL `/webhooks/creem`，密钥与 Test 环境配套。仅此 POST 路径豁免 Origin；仍执行原始 body HMAC、256 KiB 限额及环境校验。代理需保留原始 body，转发链继续遵循部署手册。200 只表示 inbox 已提交，不表示权益已授予。

本机临时 HTTPS 测试可用 `python -m scripts.run_billing_hook --env-file ../.env.commercial-test.local --port 8025` 的独立 listener，只暴露这一个 POST 路径。文件必须私密、显式指定 test 环境及已迁移数据库，进程环境不会补齐文件遗漏的配置；CREEM_ENABLED=false 时回调返回 503。不要将完整 API 或 Web 暴露给 Tunnel。结束时先禁用对应 Test webhook，再停止本任务隧道/服务，保留账务历史；重开 Tunnel 更换地址后须更新同一 webhook。

运行独立进程 `python -m app.jobs.billing --loop` 每 15 秒处理 inbox；进程重启从持久队列恢复。失败按退避最多 8 次后转 review，告警日志不输出 body/密钥。经检查修正原因后使用 `python -m app.jobs.billing --once --replay-id=LOCAL_INBOX_ID` 重放，保留累计 attempts。

每天由部署平台 scheduler 执行 `python -m app.jobs.billing --once --reconcile`，或使用 `--loop --reconcile` 的内置每日扫描（默认间隔 86,400 秒，`--reconcile-interval` 可调整但不少于 60 秒）。本代码未创建平台服务或定时任务。正常 inbox/退款取消处理仍每 15 秒一批；不要同时配多种每日调度制造重复平台请求。

对账先恢复已知 checkout/订阅和付款，再调用官方交易列表每页 100 条扫描当前 Test 商户历史，默认最多 100 页，可用 `--max-reconcile-pages` 调整至 1–1,000。每笔有付款证据的订阅交易形成持久 `reconciliation.transaction` 记录，工作进程重新查询交易/订阅详情核验后投影。未知订阅保存 `RECONCILIATION_UNBOUND` 供人工核对，不按邮箱或 metadata 猜归属；后来签名 checkout 完成绑定后，下次扫描可恢复它。

分页元数据不符、重复交易、记录总数变化、供应商失败或超过扫描上限时，`scan_complete=false`，单次 scheduler 命令返回非零，检查 `billing_reconciliation` 报告。`scan_complete` 仅表示该次分页枚举完成；队列中的授额/退款核验、部分退款与未绑定审查需另外处理。没有分页快照/游标合同，不声称跨扫描期间的新增/删除完全冻结；下次扫描从第一页重跑并去重。调度前核对容量，必要时分环境人工处理历史。完整 BA-10/16 仍需真实供应商验收。

## 恢复与限制

- request_id 在官方合同只描述追踪用途，未承诺 POST 幂等。请求发出后超时/进程终止保留 creating/uncertain，不自动重复创建。已知 provider_id 可对账；没有 provider_id 时等待签名 checkout.completed 或人工核实，不删除意图强行重购。产品 GET 的明确失败、`POST /checkouts` 明确 HTTP 400 输入拒绝标 failed，同 key 保留原结果，新 key 才能再试；其它创建状态仍 uncertain，错误正文不公开。
- 当前创建响应可能缺失可选 request_id；同步响应缺失时可保存本次 provider_id，若属性存在必须严格匹配，null/空值不算缺失。后续 GET 仍要求 provider 存储的 request_id 与本地意图一致，没有绑定证据不会按邮箱或 metadata 授额。
- checkout.completed 只绑定账户/订阅；subscription.paid 查询权威 transaction，验证金额/币种、订阅/顾客和毫秒周期后授额。缺字段/冲突重试后 review，绝不按邮箱归属。Test/sandbox 可接收，prod/local 拒绝。
- canceled 保留已付周期；expired 可能仍重试扣款，不能视为停止扣费并另开订阅。退款只撤销关联交易；部分退款进入 review，不按比例删分钟；争议阻止账号新任务，争议恢复仍须人工核对。
- 全额退款核验与 `billing_cancellations` 意图同事务保存。后台再次验证原交易、账号/订阅绑定及最新交易仍是该退款，才向原订阅提交明确 `mode=immediate` 取消；随后 GET 确认 canceled/scheduled_cancel 才记 verified。供应商失败或丢响应留 retry，下一轮先 GET；已确认停止时不再 POST。最多 8 次后 review，重复通知不清除处理历史。
- 有后续付款或已观察到更新版本后又收到陈旧快照，取消意图持久转 review，避免旧退款取消有效续费。只撤销原交易额度；没有退款/撤销其他周期。确认原因后可用 `python -m app.jobs.billing --once --replay-cancellation-id=LOCAL_ID` 人工重试，累计 attempts 保留，已 verified 不重放。恢复参数均用等号形式，兼容以短横线开头的合法 ID。原平台取消与续费没有条件式原子接口；真实联调须核对边界时刻并人工处理竞争结果，不把两次 GET 当平台事务。
- 009 有任意账务记录时拒绝降级删表。回退代码保留账本和既有权益；禁止直接删除付款/事件记录。生产尚未开放。
- 012 有任何取消意图时拒绝降级；关闭新 checkout 后继续运行兼容的 billing worker，直到既有通知/取消已确认或完成审查。取消 POST 的成功响应不代替后续 GET 核验。Portal 实测返回 canceled、已付周期结束日期保留；10月15日补验 active 退款自动发取消 POST 一次并 GET 确认，重复对账不再 POST。退款/续费竞态及多周期等分支继续待验。

## 官方合同核验

2026-10-06 实际读取以下公开原文；网页代理超时后直接读取官方 Markdown。

- https://docs.creem.io/api-reference/endpoint/create-checkout.md
- https://docs.creem.io/api-reference/endpoint/get-checkout.md
- https://docs.creem.io/api-reference/endpoint/get-subscription.md
- https://docs.creem.io/api-reference/endpoint/get-transaction.md
- https://docs.creem.io/code/webhooks.md
- https://docs.creem.io/features/customer-portal.md
- https://docs.creem.io/getting-started/test-mode.md

2026-10-07 使用 `agent-reach` 网页路由补读公开官方原文；读取代理超时后按回退直接读取官方 Markdown：

- https://docs.creem.io/api-reference/endpoint/get-transactions.md
- https://docs.creem.io/api-reference/endpoint/cancel-subscription.md
- https://docs.creem.io/features/subscriptions/refunds-and-cancellations.md
- https://docs.creem.io/api-reference/endpoint/list-customer-subscriptions.md

列表为 `GET /v1/transactions/search`，参数 `page_number/page_size`，返回 `items/pagination`（总记录/页数、当前/前后页）；取消为 `POST /v1/subscriptions/{id}/cancel`，显式 `mode=immediate`。原文读取不代表测试商户实际返回合同已验证。

账户删除还使用 `GET /v1/customers/{id}/subscriptions` 的相同分页结构核对全部已绑定订阅，再停止未来续费；未知订阅不自动按邮箱归属或取消。流程与 Worker 配置见 [认证设置](auth-setup.md)。没有绑定完整证据或仍有未知 checkout 时，删除保留处理中/审查状态。

API 固定 https://test-api.creem.io/v1，x-api-key；支付请求无重定向/自动 POST 重试，响应最多 1 MiB。签名 HMAC-SHA256(raw body)，eventType/id 防重放；订阅周期 ISO、transaction 样例为毫秒时间戳。退款样例旧值/环境 local 不作为放宽当前 API 枚举的依据。真实商户联调必须核实 Test 字段、金额税额口径和实际页面。
